import os
import requests
import pandas as pd
import json
import logging
import boto3
from datetime import datetime
from dateutil import parser
import pytz
from scripts import config

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# We'll fetch all batters (non-pitchers) and filter to top 12 by plate appearances

# Output files
output_dir = "data/postseason"
json_file = f"{output_dir}/brewers_postseason_stats_2026.json"
series_file = f"{output_dir}/brewers_postseason_series_2026.json"
pitching_file = f"{output_dir}/brewers_postseason_pitching_2026.json"
games_file = f"{output_dir}/brewers_postseason_games_2026.json"

# S3 configuration
s3_bucket = "mkebrewers-data"
s3_key_stats = "mkebrewers/data/postseason/brewers_postseason_stats_2026.json"
s3_key_series = "mkebrewers/data/postseason/brewers_postseason_series_2026.json"
s3_key_pitching = "mkebrewers/data/postseason/brewers_postseason_pitching_2026.json"
s3_key_games = "mkebrewers/data/postseason/brewers_postseason_games_2026.json"

# AWS session
is_github_actions = os.getenv('GITHUB_ACTIONS') == 'true' or os.getenv('AWS_ACCESS_KEY_ID') is not None
aws_key_id = os.environ.get("AWS_ACCESS_KEY_ID")
aws_secret_key = os.environ.get("AWS_SECRET_ACCESS_KEY")
aws_region = "us-east-2"
if is_github_actions:
    session = boto3.Session(
        aws_access_key_id=aws_key_id,
        aws_secret_access_key=aws_secret_key,
        region_name=aws_region
    )
else:
    session = boto3.Session(profile_name="default", region_name=aws_region)
s3 = session.resource('s3')

def fetch_roster_data():
    """Fetch roster data from local file or URL"""
    local_file = "_data/roster/brewers_roster_current.json"
    if os.path.exists(local_file):
        with open(local_file, 'r') as f:
            return json.load(f)
    else:
        # Fallback to URL
        s3_key_json = "https://mkebrewers-data.s3.amazonaws.com/mkebrewers/data/roster/brewers_roster_current.json"
        response = requests.get(s3_key_json)
        return response.json()

def get_all_pitchers():
    """Get all pitchers from roster data"""
    roster_df = pd.DataFrame(fetch_roster_data())
    pitchers = roster_df[roster_df['position_group'].isin(['Pitchers'])]
    if 'is_minors' in pitchers.columns:
        # Skip minor leaguers: they can't have Brewers postseason stats, and each
        # one costs an API call on every 30-minute run
        pitchers = pitchers[~pitchers['is_minors'].fillna(False).astype(bool)]
    player_ids = {row['name']: row['player_id'] for _, row in pitchers.iterrows()}
    logging.info(f"Total pitchers found: {len(player_ids)}")
    return player_ids

def get_all_batters():
    """Get all non-pitcher players from roster data"""
    roster_json = fetch_roster_data()
    roster_df = pd.DataFrame(roster_json)
    
    # Filter out pitchers and get only batters
    batters = roster_df[~roster_df['position_group'].isin(['Pitchers'])]
    
    player_ids = {}
    for _, player_row in batters.iterrows():
        player_name = player_row['name']
        player_id = player_row['player_id']
        player_ids[player_name] = player_id
        logging.info(f"Found batter {player_name}: {player_id}")
    
    logging.info(f"Total batters found: {len(player_ids)}")
    return player_ids

def get_next_game_info(series_data):
    """Get information about the next upcoming game"""
    next_game_info = None
    
    # Look for the current series (in_progress)
    current_series = None
    for series in series_data:
        if not series.get('is_over', True):
            current_series = series
            break
    
    if current_series:
        # Try to get more detailed game info from API
        try:
            # Get current series schedule to find next game
            current_year = datetime.now().year
            url = f"https://statsapi.mlb.com/api/v1/schedule/postseason?sportId=1&season={current_year}&hydrate=team,venue,linescore&language=en"
            
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()
            
            if 'dates' in data:
                for date_entry in data['dates']:
                    for game in date_entry.get('games', []):
                        home_team = game.get('teams', {}).get('home', {}).get('team', {}).get('name', '')
                        away_team = game.get('teams', {}).get('away', {}).get('team', {}).get('name', '')
                        
                        if config.TEAM_FULL_NAME in [home_team, away_team]:
                            game_status = game.get('status', {}).get('detailedState', '')
                            
                            # Look for upcoming games (Scheduled, Pre-Game, etc.)
                            if game_status in ['Scheduled', 'Pre-Game', 'Warmup']:
                                game_datetime = game.get('gameDate', '')
                                venue_name = game.get('venue', {}).get('name', '')
                                
                                if game_datetime:
                                    # Parse the game time and convert to team timezone
                                    try:
                                        game_dt = parser.parse(game_datetime)
                                        team_tz = pytz.timezone(config.TEAM_TIMEZONE)
                                        game_local = game_dt.astimezone(team_tz)

                                        next_game_info = {
                                            'opponent': away_team if home_team == config.TEAM_FULL_NAME else home_team,
                                            'venue': venue_name,
                                            'datetime_pt': game_local,
                                            'time_pt': game_local.strftime('%-I:%M p.m. CT'),
                                            'day': game_local.strftime('%A'),
                                            'is_home': home_team == config.TEAM_FULL_NAME
                                        }
                                        
                                        logging.info(f"Found next game: {next_game_info}")
                                        return next_game_info
                                        
                                    except Exception as e:
                                        logging.warning(f"Error parsing game time: {e}")
                                        
        except Exception as e:
            logging.warning(f"Error fetching detailed game info: {e}")
    
    return next_game_info


POSTSEASON_ROUNDS = {"F": "Wild Card", "D": "NLDS", "L": "NLCS", "W": "World Series"}
SCHEDULE_URL = "https://statsapi.mlb.com/api/v1/schedule"


def fetch_postseason_schedule(season=2026):
    """Every Brewers postseason game this year, with decisions and probable pitchers."""
    params = {
        "sportId": 1, "teamId": config.TEAM_ID, "season": season, "gameType": "F,D,L,W",
        "hydrate": "decisions,probablePitcher,venue,team",
    }
    resp = requests.get(SCHEDULE_URL, params=params, timeout=30)
    resp.raise_for_status()
    return [g for d in resp.json().get("dates", []) for g in d.get("games", [])]


def _sides(game):
    home, away = game["teams"]["home"], game["teams"]["away"]
    is_home = home["team"]["id"] == config.TEAM_ID
    return (home, away, is_home) if is_home else (away, home, is_home)


def summarize_postseason_games(games, tz):
    """Split postseason games into a completed-game log and the next scheduled game."""
    log, upcoming = [], []
    for g in sorted(games, key=lambda g: g.get("gameDate", "")):
        if g.get("status", {}).get("detailedState") in ("Postponed", "Cancelled"):
            continue
        mine, theirs, is_home = _sides(g)
        start = datetime.fromisoformat(g["gameDate"].replace("Z", "+00:00")).astimezone(tz)
        row = {
            "game_pk": g.get("gamePk"),
            "date": start.strftime("%b %-d"),
            "round": POSTSEASON_ROUNDS.get(g.get("gameType"), "Postseason"),
            "game_number": g.get("seriesGameNumber"),
            "opponent": theirs["team"].get("name"),
            "opponent_id": theirs["team"].get("id"),
            "home_away": "home" if is_home else "away",
            "venue": g.get("venue", {}).get("name"),
        }
        if g.get("status", {}).get("abstractGameState") == "Final":
            decisions = g.get("decisions") or {}
            row.update({
                "score": f"{mine.get('score')}-{theirs.get('score')}",
                "result": "win" if mine.get("score", 0) > theirs.get("score", 0) else "loss",
                "winning_pitcher": (decisions.get("winner") or {}).get("fullName"),
                "losing_pitcher": (decisions.get("loser") or {}).get("fullName"),
                "save_pitcher": (decisions.get("save") or {}).get("fullName"),
            })
            log.append(row)
        else:
            row.update({
                "start_time": "TBD" if g.get("startTimeTBD") else start.strftime("%-I:%M %p"),
                "day": start.strftime("%A"),
                "if_necessary": g.get("ifNecessary") == "Y",
                "brewers_probable": (mine.get("probablePitcher") or {}).get("id"),
                "opponent_probable": (theirs.get("probablePitcher") or {}).get("id"),
            })
            upcoming.append(row)

    next_game = upcoming[0] if upcoming else None
    if next_game:
        # Series score so far in the round the next game belongs to
        same_round = [r for r in log if r["round"] == next_game["round"]]
        next_game["series_wins"] = sum(r["result"] == "win" for r in same_round)
        next_game["series_losses"] = sum(r["result"] == "loss" for r in same_round)
    return log, next_game


def fetch_pitcher_line(person_id, season=2026):
    """Name, handedness and regular-season W-L/ERA for a probable starter."""
    if not person_id:
        return None
    resp = requests.get(
        f"https://statsapi.mlb.com/api/v1/people/{person_id}",
        params={"hydrate": f"stats(group=pitching,type=season,season={season})"},
        timeout=30,
    )
    resp.raise_for_status()
    person = resp.json()["people"][0]
    splits = (person.get("stats") or [{}])[0].get("splits") or [{}]
    stat = splits[0].get("stat", {})
    return {
        "id": person_id,
        "name": person.get("fullName"),
        "throws": (person.get("pitchHand") or {}).get("code"),
        "record": f"{stat.get('wins', 0)}-{stat.get('losses', 0)}" if stat else None,
        "era": stat.get("era"),
    }


def fetch_season_series(opponent_id, season=2026):
    """Regular-season head-to-head record against an opponent."""
    resp = requests.get(SCHEDULE_URL, params={
        "sportId": 1, "teamId": config.TEAM_ID, "opponentId": opponent_id, "season": season, "gameType": "R",
    }, timeout=30)
    resp.raise_for_status()
    wins = losses = 0
    for d in resp.json().get("dates", []):
        for g in d.get("games", []):
            if g.get("status", {}).get("abstractGameState") != "Final":
                continue
            mine, theirs, _ = _sides(g)
            if mine.get("score", 0) > theirs.get("score", 0):
                wins += 1
            else:
                losses += 1
    return {"wins": wins, "losses": losses}


def build_postseason_games():
    tz = pytz.timezone(config.TEAM_TIMEZONE)
    log, next_game = summarize_postseason_games(fetch_postseason_schedule(), tz)
    if next_game:
        next_game["brewers_probable"] = fetch_pitcher_line(next_game["brewers_probable"])
        next_game["opponent_probable"] = fetch_pitcher_line(next_game["opponent_probable"])
        next_game["season_series"] = fetch_season_series(next_game["opponent_id"])
    return {"games": log, "next_game": next_game}


def fetch_postseason_series():
    """Fetch postseason series data from MLB API"""
    # Try different parameter combinations to get the most current data
    urls = [
        # Most comprehensive - all postseason game types with current season
        "https://statsapi.mlb.com/api/v1/schedule/postseason/series?sportId=1&season=2026&language=en&timeZone=America/New_York&hydrate=team,linescore(matchup),flags,statusFlags,broadcasts(all),venue(location),decisions,game(content(media(epg),summary),tickets),seriesStatus(useOverride=true)&sortBy=gameDate",
        # Alternative with specific game types
        "https://statsapi.mlb.com/api/v1/schedule/postseason/series?sportId=1&gameType=D&gameType=F&gameType=L&gameType=W&season=2026&language=en&hydrate=team,seriesStatus(useOverride=true)&sortBy=gameDate",
        # Simpler call to avoid potential caching issues
        "https://statsapi.mlb.com/api/v1/schedule/postseason?sportId=1&season=2026&hydrate=team,seriesStatus&language=en"
    ]
    
    for i, url in enumerate(urls):
        try:
            logging.info(f"Trying API URL {i+1}/{len(urls)}")
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()
            
            logging.info(f"API response keys: {list(data.keys())}")
            if 'series' in data:
                logging.info(f"Found {len(data['series'])} series groups")
            
            # Extract Brewers-relevant series information
            brewers_series = []
            
            if 'series' in data:
                for series_group in data['series']:
                    if 'games' in series_group:
                        logging.info(f"Processing series group with {len(series_group['games'])} games")
                        for game in series_group['games']:
                            # Check if Team is involved
                            home_team = game.get('teams', {}).get('home', {}).get('team', {}).get('name', '')
                            away_team = game.get('teams', {}).get('away', {}).get('team', {}).get('name', '')
                            
                            if config.TEAM_FULL_NAME in [home_team, away_team]:
                                series_status = game.get('seriesStatus', {})
                                series_name = series_status.get('shortName', 'Unknown Series')
                                game_date = game.get('gameDate', '')
                                
                                logging.info(f"Found Brewers game: {series_name} on {game_date}")
                                logging.info(f"Series status: {series_status}")
                                
                                # Determine series info
                                series_info = {
                                    'series_name': series_name,
                                    'description': series_status.get('description', ''),
                                    'is_over': series_status.get('isOver', False),
                                    'result': series_status.get('result', ''),
                                    'wins': series_status.get('wins', 0),
                                    'losses': series_status.get('losses', 0),
                                    'total_games': series_status.get('totalGames', 0),
                                    'opponent': away_team if home_team == config.TEAM_FULL_NAME else home_team,
                                    'game_date': game_date,
                                    'status': game.get('status', {}).get('detailedState', ''),
                                    'game_number': series_status.get('gameNumber', 0)
                                }
                                
                                # Avoid duplicates by checking if we already have this series
                                existing_series = next((s for s in brewers_series if s['series_name'] == series_name), None)
                                if not existing_series:
                                    brewers_series.append(series_info)
                                    logging.info(f"Added new series: {series_name} vs {series_info['opponent']} - {series_info['result']}")
                                else:
                                    # Update with latest info if this game is more recent
                                    if game_date > existing_series.get('game_date', ''):
                                        existing_series.update(series_info)
                                        logging.info(f"Updated series: {series_name} with more recent data")
            
            if brewers_series:
                logging.info(f"Successfully found {len(brewers_series)} Brewers series with URL {i+1}")
                return brewers_series
            else:
                logging.warning(f"No Brewers series found with URL {i+1}")
                
        except Exception as e:
            logging.error(f"Error with API URL {i+1}: {e}")
            continue
    
    logging.error("All API URLs failed")
    return []

def fetch_postseason_stats(player_id, player_name, group='hitting', raise_on_error=False):
    """Fetch postseason stats for a specific player (group: 'hitting' or 'pitching')"""
    headers = {
        'sec-ch-ua-platform': '"macOS"',
        'Referer': f'https://www.mlb.com/player/{player_name.lower().replace(" ", "-")}-{player_id}',
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36',
        'sec-ch-ua': '"Chromium";v="140", "Not=A?Brand";v="24", "Google Chrome";v="140"',
        'sec-ch-ua-mobile': '?0',
    }
    
    url = f'https://statsapi.mlb.com/api/v1/people/{player_id}/stats?stats=yearByYear&gameType=P&leagueListId=mlb_hist&group={group}&hydrate=team(league)&language=en'
    
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        # Extract 2026 postseason stats
        stats_2026 = None
        if 'stats' in data and len(data['stats']) > 0:
            for stat_group in data['stats']:
                if stat_group['type']['displayName'] == 'yearByYear':
                    for split in stat_group['splits']:
                        if split['season'] == '2026':
                            stats_2026 = split['stat']
                            break
                    break
        
        if stats_2026:
            logging.info(f"Found 2026 postseason stats for {player_name}")
            return {
                'player_id': player_id,
                'player_name': player_name,
                'season': '2026',
                'stats': stats_2026
            }
        else:
            logging.warning(f"No 2026 postseason stats found for {player_name}")
            return None
            
    except Exception as e:
        logging.error(f"Error fetching stats for {player_name}: {e}")
        if raise_on_error:
            raise
        return None

def innings_to_outs(ip):
    """Convert baseball innings notation ('5.2' = 5 and 2/3) to outs recorded"""
    try:
        whole, _, frac = str(ip).partition('.')
        return int(whole) * 3 + int(frac or 0)
    except ValueError:
        return 0

def build_top_pitchers(limit=8):
    """Top pitchers by postseason innings pitched.

    Returns None if any request failed, so a transient API error can't replace
    good pitching data with a partial list."""
    pitchers = []
    for player_name, player_id in get_all_pitchers().items():
        try:
            stats = fetch_postseason_stats(player_id, player_name, group='pitching', raise_on_error=True)
        except Exception:
            return None
        if stats and innings_to_outs(stats['stats'].get('inningsPitched', 0)) > 0:
            pitchers.append(stats)
    pitchers.sort(
        key=lambda p: (innings_to_outs(p['stats'].get('inningsPitched', 0)), p['stats'].get('strikeOuts', 0)),
        reverse=True
    )
    return pitchers[:limit]

def main():
    """Main function to fetch all postseason stats and series data"""
    os.makedirs(output_dir, exist_ok=True)
    
    # Fetch series data
    logging.info("Fetching postseason series data...")
    series_data = fetch_postseason_series()
    
    # Get next game info with proper time zone handling
    next_game = get_next_game_info(series_data)
    
    # Create a structured playoff journey
    playoff_journey = [
        {"round": "Wild Card", "series_name": "NL Wild Card Series", "status": "upcoming", "opponent": "?", "result": "?"},
        {"round": "NLDS", "series_name": "NL Division Series", "status": "upcoming", "opponent": "?", "result": "?"},
        {"round": "NLCS", "series_name": "NL Championship Series", "status": "upcoming", "opponent": "?", "result": "?"},
        {"round": "World Series", "series_name": "World Series", "status": "upcoming", "opponent": "?", "result": "?"}
    ]
    
    # Update with actual data
    for series in series_data:
        series_name = series.get('series_name', '').lower()
        description = series.get('description', '').lower()
        
        logging.info(f"Processing series: {series_name}, description: {description}")
        
        if 'wild card' in series_name or 'wild card' in description:
            playoff_journey[0].update({
                "status": "completed" if series.get('is_over') else "in_progress",
                "opponent": series.get('opponent', '?'),
                "result": series.get('result', '?'),
                "wins": series.get('wins', 0),
                "losses": series.get('losses', 0)
            })
            logging.info(f"Updated Wild Card: {playoff_journey[0]}")
        elif 'division' in series_name or 'alds' in series_name.lower() or 'division' in description:
            playoff_journey[1].update({
                "status": "completed" if series.get('is_over') else "in_progress",
                "opponent": series.get('opponent', '?'),
                "result": series.get('result', '?'),
                "wins": series.get('wins', 0),
                "losses": series.get('losses', 0)
            })
            logging.info(f"Updated NLDS: {playoff_journey[1]}")
        elif 'championship' in series_name or 'alcs' in series_name.lower() or 'championship' in description:
            playoff_journey[2].update({
                "status": "completed" if series.get('is_over') else "in_progress",
                "opponent": series.get('opponent', '?'),
                "result": series.get('result', '?'),
                "wins": series.get('wins', 0),
                "losses": series.get('losses', 0)
            })
            logging.info(f"Updated NLCS: {playoff_journey[2]}")
        elif 'world series' in series_name or 'world series' in description:
            playoff_journey[3].update({
                "status": "completed" if series.get('is_over') else "in_progress",
                "opponent": series.get('opponent', '?'),
                "result": series.get('result', '?'),
                "wins": series.get('wins', 0),
                "losses": series.get('losses', 0)
            })
            logging.info(f"Updated World Series: {playoff_journey[3]}")
        else:
            logging.warning(f"Could not categorize series: {series_name} - {description}")
    
    # A team that skips the Wild Card Series (a top-two seed) never appears in it, so once a
    # later round has started, mark the Wild Card round as a bye instead of leaving it "upcoming"
    if playoff_journey[0]["status"] == "upcoming" and any(r["status"] != "upcoming" for r in playoff_journey[1:]):
        playoff_journey[0].update({"status": "bye", "opponent": "", "result": "Top-two seed"})

    # Note: Manual overrides removed to allow live API data to flow through
    # The API now correctly provides real-time series status
    logging.info("Using live API data without manual overrides")
    
    # Save series data
    with open(series_file, 'w', encoding='utf-8') as f:
        json.dump(playoff_journey, f, indent=2, ensure_ascii=False)
    
    logging.info(f"Saved postseason series data to {series_file}")
    
    # Fetch player stats
    player_ids = get_all_batters()
    all_stats = []
    
    # Fetch stats for all batters
    for player_name, player_id in player_ids.items():
        stats = fetch_postseason_stats(player_id, player_name)
        if stats:
            all_stats.append(stats)
    
    # Filter to top 12 by plate appearances (plateAppearances)
    # Sort by plate appearances descending, then take top 12
    all_stats_with_pa = []
    for player_stats in all_stats:
        stats = player_stats['stats']
        plate_appearances = stats.get('plateAppearances', 0)
        if plate_appearances > 0:  # Only include players with postseason PAs
            player_stats['plate_appearances'] = plate_appearances
            all_stats_with_pa.append(player_stats)
    
    # Sort by plate appearances (descending) and take top 12
    top_12_stats = sorted(all_stats_with_pa, key=lambda x: x['plate_appearances'], reverse=True)[:12]
    
    # Remove the temporary plate_appearances field before saving
    for player_stats in top_12_stats:
        if 'plate_appearances' in player_stats:
            del player_stats['plate_appearances']
    
    # Save to JSON file
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(top_12_stats, f, indent=2, ensure_ascii=False)
    
    logging.info(f"Saved postseason stats for top {len(top_12_stats)} players (by plate appearances) to {json_file}")

    # Pitching: top 8 by innings pitched. Isolated so a failure here can't block
    # the series and hitting uploads below.
    top_pitchers = None
    try:
        top_pitchers = build_top_pitchers()
        if top_pitchers is None:
            logging.warning("Skipping postseason pitching update: an API request failed")
        else:
            with open(pitching_file, 'w', encoding='utf-8') as f:
                json.dump(top_pitchers, f, indent=2, ensure_ascii=False)
            logging.info(f"Saved postseason pitching stats for {len(top_pitchers)} pitchers (by innings pitched) to {pitching_file}")
    except Exception as e:
        logging.error(f"Postseason pitching update failed: {e}")
        top_pitchers = None

    # Game log and next-game preview. Isolated like pitching so a failure can't block other uploads.
    try:
        postseason_games = build_postseason_games()
        with open(games_file, 'w', encoding='utf-8') as f:
            json.dump(postseason_games, f, indent=2, ensure_ascii=False)
        s3.Bucket(s3_bucket).upload_file(games_file, s3_key_games)
        logging.info(f"Saved {len(postseason_games['games'])} postseason games and next-game preview to {games_file}")
    except Exception as e:
        logging.error(f"Postseason game log update failed: {e}")

    # Upload to S3
    try:
        s3.Bucket(s3_bucket).upload_file(series_file, s3_key_series)
        logging.info(f"Uploaded {series_file} to S3: s3://{s3_bucket}/{s3_key_series}")

        s3.Bucket(s3_bucket).upload_file(json_file, s3_key_stats)
        logging.info(f"Uploaded {json_file} to S3: s3://{s3_bucket}/{s3_key_stats}")
    except Exception as e:
        logging.error(f"Failed to upload to S3: {e}")

    if top_pitchers is not None:
        try:
            s3.Bucket(s3_bucket).upload_file(pitching_file, s3_key_pitching)
            logging.info(f"Uploaded {pitching_file} to S3: s3://{s3_bucket}/{s3_key_pitching}")
        except Exception as e:
            logging.error(f"Failed to upload pitching stats to S3: {e}")

    # Print summary
    print(f"\n=== {config.TEAM_NAME} 2026 Postseason Journey ===")
    for journey in playoff_journey:
        status_icon = "✅" if journey['status'] == "completed" else "🏃" if journey['status'] == "in_progress" else "❓"
        print(f"{status_icon} {journey['round']}: vs {journey['opponent']} - {journey['result']}")
    
    # Enhanced current status with context
    current_series = None
    previous_series = None
    
    # Find current and most recent completed series
    for journey in playoff_journey:
        if journey['status'] == 'in_progress':
            current_series = journey
        elif journey['status'] == 'completed':
            if previous_series is None or journey['round'] in ['World Series', 'NLCS', 'NLDS', 'Wild Card']:
                # Get the most recent completed series
                round_order = {'Wild Card': 1, 'NLDS': 2, 'NLCS': 3, 'World Series': 4}
                if previous_series is None or round_order.get(journey['round'], 0) > round_order.get(previous_series['round'], 0):
                    previous_series = journey
    
    if next_game:
        game_time = next_game['time_pt']
        game_day = next_game['day']
        venue = next_game['venue']
        current_opponent = next_game['opponent']
        
        print(f"\n📅 Current Status: NLCS Game 1 vs {current_opponent} starts {game_day} at {game_time}")
        print(f"🏟️ Venue: {venue}")
        
        if previous_series and previous_series['opponent'] != current_opponent:
            print(f"🏆 Last completed series: {previous_series['round']} vs {previous_series['opponent']} ({previous_series['result']})")
    else:
        # Fallback if we can't get detailed game info
        if current_series:
            print(f"\n📅 Current Status: {current_series['round']} vs {current_series['opponent']} - {current_series['result']}")
        if previous_series:
            print(f"🏆 Last completed series: {previous_series['round']} vs {previous_series['opponent']} ({previous_series['result']})")
    
    print(f"\n=== Top {len(top_12_stats)} Players by 2026 Postseason Plate Appearances ===")
    for i, player_stats in enumerate(top_12_stats, 1):
        name = player_stats['player_name']
        stats = player_stats['stats']
        avg = stats.get('avg', '.000')
        hr = stats.get('homeRuns', 0)
        rbi = stats.get('rbi', 0)
        pa = stats.get('plateAppearances', 0)
        games = stats.get('gamesPlayed', 0)
        print(f"{i:2d}. {name}: {games}G, {pa} PA, {avg} AVG, {hr} HR, {rbi} RBI")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logging.error(f"Script failed: {e}")
        import sys; sys.exit(1)