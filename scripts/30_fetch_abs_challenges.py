"""Collect ABS (Automated Ball-Strike) challenges from every Brewers game this season.

Each challenge is read from the MLB live game feed, where a challenged pitch
carries `reviewDetails` (reviewType "MJ") naming the challenging team and
player and whether the call was overturned. The raw challenges and a summary
split into regular season and postseason are written locally and to S3.
"""
import json
import logging
import os

import boto3
import requests

from scripts import config

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

SCHEDULE_URL = "https://statsapi.mlb.com/api/v1/schedule"
FEED_URL = "https://statsapi.mlb.com/api/v1.1/game/{game_pk}/feed/live"
ABS_REVIEW_TYPE = "MJ"
POSTSEASON_GAME_TYPES = {"F", "D", "L", "W"}

year = config.CURRENT_YEAR
output_dir = "data/abs"
challenges_file = f"{output_dir}/brewers_abs_challenges_{year}.json"
summary_file = f"{output_dir}/brewers_abs_summary_{year}.json"

s3_bucket = "mkebrewers-data"
s3_key_challenges = f"mkebrewers/data/abs/brewers_abs_challenges_{year}.json"
s3_key_summary = f"mkebrewers/data/abs/brewers_abs_summary_{year}.json"
public_challenges_url = f"https://{s3_bucket}.s3.amazonaws.com/{s3_key_challenges}"


def get_s3():
    is_github_actions = os.getenv('GITHUB_ACTIONS') == 'true' or os.getenv('AWS_ACCESS_KEY_ID') is not None
    if is_github_actions:
        session = boto3.Session(
            aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
            region_name="us-east-2",
        )
    else:
        session = boto3.Session(profile_name="default", region_name="us-east-2")
    return session.resource('s3')


def season_type(game_type):
    return "postseason" if game_type in POSTSEASON_GAME_TYPES else "regular"


def fetch_final_games():
    """Return the season's completed Brewers regular season and postseason games."""
    params = {
        "sportId": 1,
        "teamId": config.TEAM_ID,
        "season": year,
        "gameType": "R,F,D,L,W",
    }
    resp = requests.get(SCHEDULE_URL, params=params, timeout=30)
    resp.raise_for_status()
    games = []
    for date in resp.json().get("dates", []):
        for g in date.get("games", []):
            if g.get("status", {}).get("abstractGameState") != "Final":
                continue
            if g.get("status", {}).get("detailedState") in ("Postponed", "Cancelled"):
                continue
            games.append({
                "game_pk": g["gamePk"],
                "game_date": g.get("officialDate"),
                "game_type": g.get("gameType"),
            })
    return games


def challenger_role(challenger_id, batter_id, pitcher_id):
    # Only the batter, pitcher or catcher may challenge, so anyone else is the catcher
    if challenger_id == batter_id:
        return "Batter"
    if challenger_id == pitcher_id:
        return "Pitcher"
    return "Catcher"


def is_abs_review(review):
    return bool(review) and review.get("reviewType") == ABS_REVIEW_TYPE


def challenged_pitches(play):
    """Yield (pitch event, review) for each ABS challenge in a plate appearance.

    Most challenges sit on the pitch itself, but a challenge of the pitch that
    ends the plate appearance (strike three or ball four) is recorded on the
    play instead, and applies to its final pitch.
    """
    pitches = [e for e in play.get("playEvents", []) if e.get("isPitch")]
    for event in pitches:
        if is_abs_review(event.get("reviewDetails")):
            yield event, event["reviewDetails"]
    play_review = play.get("reviewDetails")
    if is_abs_review(play_review) and pitches and not is_abs_review(pitches[-1].get("reviewDetails")):
        yield pitches[-1], play_review


def extract_challenges(feed, game):
    """Pull every ABS challenge (by either team) out of a live game feed."""
    teams = feed.get("gameData", {}).get("teams", {})
    home_id = teams.get("home", {}).get("id")
    is_home = home_id == config.TEAM_ID
    opp = teams.get("away" if is_home else "home", {})

    rows = []
    for play in feed.get("liveData", {}).get("plays", {}).get("allPlays", []):
        about = play.get("about", {})
        matchup = play.get("matchup", {})
        batter = matchup.get("batter", {})
        pitcher = matchup.get("pitcher", {})
        for event, review in challenged_pitches(play):
            if review.get("inProgress"):
                continue
            challenger = review.get("player", {})
            team_id = review.get("challengeTeamId")
            details = event.get("details", {})
            coords = event.get("pitchData", {}).get("coordinates", {})
            # The feed records the final call, so an overturned pitch's original call is the opposite
            final_call = details.get("call", {}).get("description") or details.get("description")
            is_strike = bool(details.get("isStrike"))
            overturned = bool(review.get("isOverturned"))
            if overturned and final_call:
                original_call = "Ball" if is_strike else "Called Strike"
            else:
                original_call = final_call
            # The event's count already includes this pitch; back it out to get the count when challenged
            count = event.get("count", {})
            balls = count.get("balls")
            strikes = count.get("strikes")
            if balls is not None and strikes is not None:
                if is_strike:
                    strikes = max(0, strikes - 1)
                else:
                    balls = max(0, balls - 1)
            rows.append({
                "game_pk": game["game_pk"],
                "game_date": game["game_date"],
                "game_type": game["game_type"],
                "season_type": season_type(game["game_type"]),
                "opponent": opp.get("abbreviation") or opp.get("teamName") or opp.get("name"),
                "home_away": "home" if is_home else "away",
                "inning": about.get("inning"),
                "half_inning": about.get("halfInning"),
                "challenging_team": "brewers" if team_id == config.TEAM_ID else "opponent",
                "challenger": challenger.get("fullName"),
                "challenger_id": challenger.get("id"),
                "challenger_role": challenger_role(challenger.get("id"), batter.get("id"), pitcher.get("id")),
                "batter": batter.get("fullName"),
                "pitcher": pitcher.get("fullName"),
                "balls": balls,
                "strikes": strikes,
                "outs": count.get("outs"),
                "original_call": original_call,
                "final_call": final_call,
                "overturned": overturned,
                "pitch_type": details.get("type", {}).get("description"),
                "px": coords.get("pX"),
                "pz": coords.get("pZ"),
                "play_id": event.get("playId"),
            })
    return rows


def tally(rows):
    total = len(rows)
    won = sum(1 for r in rows if r["overturned"])
    return {
        "challenges": total,
        "overturned": won,
        "upheld": total - won,
        "success_rate": round(won / total, 3) if total else None,
    }


def inning_label(inning):
    if inning is None:
        return None
    return "10+" if inning >= 10 else str(inning)


def summarize_split(rows, games_played):
    brewers = [r for r in rows if r["challenging_team"] == "brewers"]
    opponents = [r for r in rows if r["challenging_team"] == "opponent"]

    by_inning = []
    for label in [str(i) for i in range(1, 10)] + ["10+"]:
        inning_rows = [r for r in brewers if inning_label(r["inning"]) == label]
        by_inning.append(dict(inning=label, **tally(inning_rows)))

    players = {}
    for r in brewers:
        p = players.setdefault(r["challenger_id"], {"name": r["challenger"], "rows": []})
        p["rows"].append(r)
    by_player = []
    for p in players.values():
        entry = {"name": p["name"]}
        entry.update(tally(p["rows"]))
        # Batters challenge on offense; catchers and pitchers challenge on defense
        entry["offense"] = tally([r for r in p["rows"] if r["challenger_role"] == "Batter"])
        entry["defense"] = tally([r for r in p["rows"] if r["challenger_role"] != "Batter"])
        by_player.append(entry)
    by_player.sort(key=lambda e: (-e["challenges"], -e["overturned"], e["name"] or ""))

    return {
        "games": games_played,
        "brewers": tally(brewers),
        "opponents": tally(opponents),
        "brewers_by_inning": by_inning,
        "brewers_by_player": by_player,
    }


def build_summary(rows, games):
    summary = {}
    for split in ("regular", "postseason"):
        split_games = [g for g in games if season_type(g["game_type"]) == split]
        split_rows = [r for r in rows if r["season_type"] == split]
        summary[split] = summarize_split(split_rows, len(split_games))
    return summary


def load_existing():
    try:
        resp = requests.get(public_challenges_url, timeout=15)
        if resp.status_code == 200 and resp.content:
            return resp.json()
    except Exception as e:
        logging.warning(f"Could not load existing challenges: {e}")
    return []


def main():
    games = fetch_final_games()
    logging.info(f"Found {len(games)} completed games")

    # Only fetch games not already in the published file; the rare game with no
    # challenges is simply refetched each run
    rows = load_existing()
    done = {r["game_pk"] for r in rows}
    new_games = [g for g in games if g["game_pk"] not in done]

    for game in new_games:
        try:
            resp = requests.get(FEED_URL.format(game_pk=game["game_pk"]), timeout=30)
            resp.raise_for_status()
        except requests.RequestException as e:
            logging.warning(f"Failed to fetch feed for {game['game_pk']}: {e}")
            continue
        game_rows = extract_challenges(resp.json(), game)
        logging.info(f"{game['game_date']} ({game['game_pk']}): {len(game_rows)} challenges")
        rows.extend(game_rows)

    rows.sort(key=lambda r: (r["game_date"], r["game_pk"], r["inning"] or 0))
    summary = build_summary(rows, games)

    os.makedirs(output_dir, exist_ok=True)
    with open(challenges_file, "w") as f:
        json.dump(rows, f, indent=2)
    with open(summary_file, "w") as f:
        json.dump(summary, f, indent=2)
    logging.info(f"Saved {len(rows)} challenges to {challenges_file} and summary to {summary_file}")

    try:
        s3 = get_s3()
        s3.Bucket(s3_bucket).upload_file(challenges_file, s3_key_challenges)
        s3.Bucket(s3_bucket).upload_file(summary_file, s3_key_summary)
        logging.info("Uploaded ABS challenge files to S3")
    except Exception as e:
        logging.error(f"Failed to upload to S3: {e}")


if __name__ == "__main__":
    main()
