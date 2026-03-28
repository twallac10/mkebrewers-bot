#!/usr/bin/env python
# coding: utf-8

"""
Fetches daily team summary data and posts updates to Bluesky.
"""

import os
import re
import json
import argparse
import logging
from datetime import datetime
import requests
from atproto import Client
import boto3
from botocore.exceptions import ClientError
from zoneinfo import ZoneInfo
from scripts import config

# --- Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Environment Variables & AWS/S3 ---
is_github_actions = os.getenv('GITHUB_ACTIONS') == 'true'
s3_bucket_name = "redsox-data"

if is_github_actions:
    session = boto3.Session(
        region_name="us-west-1"
    )
    logging.info("Running in GitHub Actions. Using environment variables for AWS credentials.")
else:
    profile_name = os.environ.get("AWS_PERSONAL_PROFILE", "haekeo")
    session = boto3.Session(profile_name=profile_name, region_name="us-west-1")
    logging.info(f"Running locally. Using AWS profile: {profile_name}")

s3_resource = session.resource("s3")

# --- Bluesky & S3 Functions ---
def get_last_post_date(post_type):
    """Reads the last post date for a given type from S3."""
    s3_key = f"redsox/data/bluesky/last_post_date_{post_type}.txt"
    try:
        obj = s3_resource.Object(s3_bucket_name, s3_key)
        last_date_str = obj.get()['Body'].read().decode('utf-8').strip()
        logging.info(f"Last post date for '{post_type}' found in S3: {last_date_str}")
        return last_date_str
    except ClientError as e:
        if e.response['Error']['Code'] == 'NoSuchKey':
            logging.info(f"{s3_key} not found. This is expected for the first run of the day.")
            return None
        else:
            logging.error(f"An unexpected S3 error occurred in get_last_post_date: {e}")
            raise

def set_last_post_date(date_str, post_type):
    """Writes the last post date for a given type to S3."""
    s3_key = f"redsox/data/bluesky/last_post_date_{post_type}.txt"
    try:
        obj = s3_resource.Object(s3_bucket_name, s3_key)
        obj.put(Body=date_str)
        logging.info(f"Successfully updated last post date in S3 for '{post_type}' to: {date_str}")
    except Exception as e:
        logging.error(f"Failed to write last post date to S3: {e}")

def post_to_bluesky(post_text, post_type):
    """Posts to Bluesky and updates the last post date on success."""
    BLUESKY_HANDLE = os.environ.get("BLUESKY_HANDLE")
    BLUESKY_APP_PASSWORD = os.environ.get("BLUESKY_APP_PASSWORD")

    if not all([BLUESKY_HANDLE, BLUESKY_APP_PASSWORD]):
        logging.error("Bluesky credentials are not fully set. Cannot post.")
        return

    try:
        client = Client()
        client.login(BLUESKY_HANDLE, BLUESKY_APP_PASSWORD)
        response = client.send_post(text=post_text)
        logging.info(f"Post published successfully to Bluesky: {response.uri}")
        # Use timezone-aware date for setting last post
        team_tz = ZoneInfo(config.TEAM_TIMEZONE)
        today_str = datetime.now(team_tz).strftime('%Y-%m-%d')
        set_last_post_date(today_str, post_type)
    except Exception as e:
        logging.error(f"Failed to post to Bluesky: {e}")

# --- Main Logic ---
def determine_summary_type():
    """Determines which type of summary to post based on current time in Team Timezone."""
    team_tz = ZoneInfo(config.TEAM_TIMEZONE)
    current_hour = datetime.now(team_tz).hour

    if 8 <= current_hour < 11:
        return 'summary'
    elif 11 <= current_hour < 14:
        return 'batting'
    elif 14 <= current_hour < 17:
        return 'pitching'
    else:
        # Outside prime hours, check what hasn't been posted today
        today_str = datetime.now(team_tz).strftime('%Y-%m-%d')

        # Check in order of priority: summary, batting, pitching
        for post_type in ['summary', 'batting', 'pitching']:
            last_post_date = get_last_post_date(post_type)
            if last_post_date != today_str:
                logging.info(f"Outside prime hours, posting {post_type} (not yet posted today)")
                return post_type

        # All have been posted today
        logging.info("All summary types have been posted today")
        return None

def main():
    parser = argparse.ArgumentParser(description="Post daily Red Sox summary updates to Bluesky.")
    parser.add_argument("--type", type=str, required=True, choices=['auto', 'summary', 'batting', 'pitching'], help="The type of update to post. Use 'auto' to determine based on time.")
    args = parser.parse_args()

    # Use timezone-aware date for all checks
    team_tz = ZoneInfo(config.TEAM_TIMEZONE)
    today_date = datetime.now(team_tz).date()
    today_str = today_date.strftime('%Y-%m-%d')

    # Determine the summary type to post
    if args.type == 'auto':
        summary_type = determine_summary_type()
        if summary_type is None:
            logging.info("No summary type determined for posting. Exiting.")
            return
    else:
        summary_type = args.type

    # Check if we've already posted this type of update today
    last_post_date = get_last_post_date(summary_type)
    if last_post_date == today_str:
        logging.info(f"An update of type '{summary_type}' has already been posted today. Skipping.")
        return

    logging.info(f"Proceeding to post summary of type: {summary_type}")

    # Fetch data
    url = "https://redsox-data.s3.amazonaws.com/redsox/data/standings/season_summary_latest.json"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.RequestException as e:
        logging.error(f"Failed to fetch data from {url}: {e}")
        return

    # Process data into a dictionary for easy access
    stats = {item['stat']: item for item in data}
    post_text = ""

    # Format post based on type
    if summary_type == 'summary':
        summary_html = stats.get('summary', {}).get('value', 'No summary available.')

        # Extract date from summary to ensure we're not posting about a future/off-season game
        date_match = re.search(r"\((\w+\s\d+)\)", summary_html)
        if date_match:
            game_date_str = date_match.group(1)
            # Check if this is a month+year (off-season) or month+day (game day)
            # If it's 4 digits, it's a year (e.g., "February 2026"), skip posting
            if re.search(r'\d{4}', game_date_str):
                logging.info(f"Off-season summary detected ({game_date_str}). Skipping post.")
                return

            # Get current year since it's not in the string
            current_year = today_date.year
            try:
                game_date = datetime.strptime(f"{game_date_str} {current_year}", "%B %d %Y").date()
                if game_date != today_date:
                    logging.info(f"Game date ({game_date}) is not today. Halting post.")
                    return
            except ValueError:
                logging.warning(f"Could not parse date from summary: {game_date_str}. Skipping date check.")
                # Continue anyway - might be a valid off-season or special summary

        summary_text = re.sub('<[^<]+?>', '', summary_html).replace('\\/','/')
        post_text = f"⚾️ {config.TEAM_NAME_SIMPLE} daily summary ⚾️\n\n{summary_text}"

    elif summary_type == 'batting':
        ba = stats.get('batting_average', {}).get('value', 'N/A')
        obp = stats.get('on_base_pct', {}).get('value', 'N/A')
        hr = stats.get('home_runs', {})
        hr_val = hr.get('value', 'N/A')
        hr_rank = hr.get('context_value', 'N/A')
        sb = stats.get('stolen_bases', {})
        sb_val = sb.get('value', 'N/A')
        sb_rank = sb.get('context_value', 'N/A')
        post_text = (
            f"⚾️ {config.TEAM_NAME_SIMPLE} batting report ⚾️\n\n"
            f"• BA: {ba}\n"
            f"• OBP: {obp}\n"
            f"• Home Runs: {hr_val} ({hr_rank} in MLB)\n"
            f"• Stolen Bases: {sb_val} ({sb_rank} in MLB)\n\n"
            f"More: https://redsox.bot"
        )

    elif summary_type == 'pitching':
        era = stats.get('era', {})
        era_val = era.get('value', 'N/A')
        era_rank = era.get('context_value', 'N/A')
        so = stats.get('strikeouts', {})
        so_val = so.get('value', 'N/A')
        so_rank = so.get('context_value', 'N/A')
        walks = stats.get('walks', {})
        walks_val = walks.get('value', 'N/A')
        walks_rank = walks.get('context_value', 'N/A')
        post_text = (
            f"⚾️ {config.TEAM_NAME_SIMPLE} pitching report ⚾️\n\n"
            f"• ERA: {era_val} ({era_rank} in MLB)\n"
            f"• Strikeouts: {so_val} ({so_rank} in MLB)\n"
            f"• Walks: {walks_val} ({walks_rank} in MLB)\n\n"
            f"More: https://redsox.bot"
        )

    if post_text:
        logging.info(f"Generated post for type '{summary_type}':\n{post_text}")
        post_to_bluesky(post_text, summary_type)
    else:
        logging.error("Failed to generate post text.")

if __name__ == "__main__":
    main()
