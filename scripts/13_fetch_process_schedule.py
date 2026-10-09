#!/usr/bin/env python
# coding: utf-8

"""
Milwaukee Brewers schedule snapshot
Builds the results/schedule tables (last 10 games and next 10 games) from the MLB Stats API, which
covers the regular season and the postseason. Upcoming games that are only played if a series goes
long are flagged with `if_necessary`.
"""

import logging
import os
from datetime import datetime
from io import BytesIO
from zoneinfo import ZoneInfo

import boto3
import pandas as pd
import requests

from scripts import config

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

SCHEDULE_URL = "https://statsapi.mlb.com/api/v1/schedule"
# Regular season plus every postseason round: wild card, division series, LCS, World Series
GAME_TYPES = "R,F,D,L,W"
SKIPPED_STATES = {"Postponed", "Cancelled"}
GAMES_PER_TABLE = 10

s3_bucket = "mkebrewers-data"
s3_base_path = "mkebrewers/data/standings/brewers_schedule"


def get_s3_resource():
    is_github_actions = os.getenv('GITHUB_ACTIONS') == 'true' or os.getenv('AWS_ACCESS_KEY_ID') is not None
    if is_github_actions:
        session = boto3.Session(
            aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
            region_name="us-east-2",
        )
    else:
        session = boto3.Session(profile_name="default", region_name="us-east-2")
    return session.resource("s3")


def fetch_schedule(year):
    params = {
        "sportId": 1,
        "teamId": config.TEAM_ID,
        "season": year,
        "gameType": GAME_TYPES,
    }
    resp = requests.get(SCHEDULE_URL, params=params, timeout=30)
    resp.raise_for_status()
    return [g for d in resp.json().get("dates", []) for g in d.get("games", [])]


def format_game_start(game, tz):
    """Local start time such as '6:10 PM', or 'TBD' when MLB hasn't set one."""
    if game.get("startTimeTBD") or not game.get("gameDate"):
        return "TBD"
    start = datetime.fromisoformat(game["gameDate"].replace("Z", "+00:00")).astimezone(tz)
    return start.strftime("%-I:%M %p")


def build_schedule(games, tz=None):
    """Turn raw MLB schedule games into the last-10 and next-10 rows the site displays."""
    tz = tz or ZoneInfo(config.TEAM_TIMEZONE)
    rows = []
    for g in sorted(games, key=lambda g: g.get("gameDate", "")):
        if g.get("status", {}).get("detailedState") in SKIPPED_STATES:
            continue
        home = g["teams"]["home"]
        away = g["teams"]["away"]
        is_home = home["team"]["id"] == config.TEAM_ID
        mine, theirs = (home, away) if is_home else (away, home)
        completed = g["status"].get("abstractGameState") == "Final"

        if completed:
            result = "win" if mine.get("score", 0) > theirs.get("score", 0) else "loss"
            game_start = f"{mine.get('score')}-{theirs.get('score')}"
        else:
            result = "--"
            game_start = format_game_start(g, tz)

        rows.append({
            "date": datetime.strptime(g["officialDate"], "%Y-%m-%d").strftime("%b %-d"),
            "opp_name": theirs["team"]["name"],
            "home_away": "home" if is_home else "away",
            "result": result,
            "game_start": game_start,
            "if_necessary": g.get("ifNecessary") == "Y",
            "completed": completed,
        })

    last = [dict(r, placement="last") for r in rows if r["completed"]][-GAMES_PER_TABLE:]
    upcoming = [dict(r, placement="next") for r in rows if not r["completed"]][:GAMES_PER_TABLE]
    columns = ["date", "opp_name", "home_away", "result", "placement", "game_start", "if_necessary"]
    return pd.DataFrame(last + upcoming, columns=columns)


def save_to_s3(df, s3_resource, formats=("csv", "json")):
    for fmt in formats:
        try:
            buffer = BytesIO()
            if fmt == "csv":
                df.to_csv(buffer, index=False)
                content_type = "text/csv"
            else:
                df.to_json(buffer, indent=4, orient="records", lines=False)
                content_type = "application/json"
            buffer.seek(0)
            s3_resource.Bucket(s3_bucket).put_object(Key=f"{s3_base_path}.{fmt}", Body=buffer, ContentType=content_type)
            logging.info(f"Uploaded {fmt} to {s3_bucket}/{s3_base_path}.{fmt}")
        except Exception as e:
            logging.error(f"Failed to upload {fmt} to S3: {e}")


def main():
    games = fetch_schedule(config.CURRENT_YEAR)
    if not games:
        logging.warning(f"Schedule not available yet for {config.CURRENT_YEAR}. Exiting without saving.")
        return
    schedule_df = build_schedule(games)
    logging.info(f"Schedule rows:\n{schedule_df}")
    save_to_s3(schedule_df, get_s3_resource())


if __name__ == "__main__":
    main()
