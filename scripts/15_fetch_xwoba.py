#!/usr/bin/env python
# coding: utf-8

"""
Milwaukee Brewers xwOBA Data
This script downloads xwOBA data from Baseball Savant for all current Brewers players.
"""

import os
import sys
import requests
import pandas as pd
from bs4 import BeautifulSoup
import json
import time
import boto3
import logging
from io import StringIO
from datetime import datetime
import re
import unicodedata

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

from scripts import config

# Using config.CURRENT_YEAR - set to 2025 for off-season, update to 2026 when season starts
CURRENT_YEAR = config.CURRENT_YEAR

# Configuration
output_dir = "data/batting"
csv_file = f"{output_dir}/brewers_xwoba_current.csv"
json_file = f"{output_dir}/brewers_xwoba_current.json"
parquet_file = f"{output_dir}/brewers_xwoba_current.parquet"
s3_bucket = "mkebrewers-data"
s3_key_csv = "mkebrewers/data/batting/brewers_xwoba_current.csv"
s3_key_json = "mkebrewers/data/batting/brewers_xwoba_current.json"
s3_key_parquet = "mkebrewers/data/batting/brewers_xwoba_current.parquet"

# Manual override: names here are always included, filled up to TOP_N with
# the highest-plate-appearance hitters on the current roster. Starts empty
# on purpose — add a name here to force-include a specific player
# regardless of playing time (e.g. a notable rookie call-up).
PIN_BATTERS = []

# Total number of batters to feature (pins + auto-filled by plate appearances).
TOP_N = 12

# Known corrections to help match allowlist typos or alternate spellings
NAME_CORRECTIONS = {
    # normalized "first last" -> corrected normalized "first last"
}

# AWS session and S3 resource
# Determine if running in a GitHub Actions environment
is_github_actions = os.getenv('GITHUB_ACTIONS') == 'true' or os.getenv('AWS_ACCESS_KEY_ID') is not None

# AWS credentials and session initialization
aws_key_id = os.environ.get("AWS_ACCESS_KEY_ID")
aws_secret_key = os.environ.get("AWS_SECRET_ACCESS_KEY")
aws_region = "us-east-2"

# Conditional AWS session creation based on the environment
if is_github_actions:
    # In GitHub Actions, use environment variables directly
    session = boto3.Session(
        aws_access_key_id=aws_key_id,
        aws_secret_access_key=aws_secret_key,
        region_name=aws_region
    )
else:
    # Locally, use a specific profile
    session = boto3.Session(profile_name="default", region_name=aws_region)

s3 = session.resource('s3')

headers = {
    'sec-ch-ua-platform': '"macOS"',
    'Referer': 'https://baseballsavant.mlb.com/savant-player/shohei-ohtani-660271?stats=career-r-hitting-mlb',
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36',
    'sec-ch-ua': '"Not A(Brand";v="8", "Chromium";v="132", "Google Chrome";v="132"',
    'sec-ch-ua-mobile': '?0',
}

def format_player_name(name):
    """Convert 'Lastname, Firstname' to 'Firstname Lastname'."""
    if ',' in name:
        last, first = name.split(',')
        return f"{first.strip()} {last.strip()}"
    return name

def strip_accents(text: str) -> str:
    """Remove diacritics from text."""
    text_norm = unicodedata.normalize('NFD', text)
    return ''.join(ch for ch in text_norm if not unicodedata.combining(ch))

def normalize_name(name: str) -> str:
    """
    Normalize a player name for comparison:
    - lower case
    - remove accents
    - remove punctuation, commas, periods
    - collapse whitespace
    - remove hyphens
    Output as "first last" order regardless of input.
    """
    if not name:
        return ""
    name = name.strip()
    # If "Last, First" flip to "First Last"
    if ',' in name:
        parts = [p.strip() for p in name.split(',')]
        if len(parts) >= 2:
            name = f"{parts[1]} {parts[0]}"
    # Remove accents
    name = strip_accents(name)
    # Remove punctuation and hyphens
    name = re.sub(r"[\-\.]+", " ", name)
    name = re.sub(r"[^a-zA-Z\s]", " ", name)
    # Collapse whitespace
    name = re.sub(r"\s+", " ", name).strip()
    return name.lower()

def to_last_first(name: str) -> str:
    """Convert "First Last" to "Last, First" for display."""
    if not name:
        return name
    tokens = name.strip().split()
    if len(tokens) >= 2:
        first = " ".join(tokens[:-1])
        last = tokens[-1]
        return f"{last}, {first}"
    return name

def match_pins(hitters, pin_names):
    """
    Match manually pinned names against the current roster's hitters.
    hitters: list of {"name": str, "id": str, "pa": int}
    pin_names: list of raw names (e.g. "First Last") to force-include
    Returns: dict {name: id} for every pin that matched a current hitter.
    Unmatched pin names are skipped (the player isn't on the roster).
    """
    pinned = {}
    normalized_hitters = []
    for h in hitters:
        normalized = normalize_name(h["name"])
        normalized = NAME_CORRECTIONS.get(normalized, normalized)
        normalized_hitters.append((normalized, h))

    for pin in pin_names:
        pin_normalized = normalize_name(pin)
        pin_normalized = NAME_CORRECTIONS.get(pin_normalized, pin_normalized)
        matched_hitter = next(
            (h for normalized, h in normalized_hitters if normalized == pin_normalized),
            None,
        )

        if matched_hitter is None:
            pin_tokens = pin_normalized.split()
            if len(pin_tokens) >= 2:
                pin_first, pin_last = " ".join(pin_tokens[:-1]), pin_tokens[-1]
                for normalized, h in normalized_hitters:
                    h_tokens = normalized.split()
                    if len(h_tokens) >= 2:
                        h_first, h_last = " ".join(h_tokens[:-1]), h_tokens[-1]
                        if h_last == pin_last and (
                            pin_first.startswith(h_first) or h_first.startswith(pin_first)
                        ):
                            matched_hitter = h
                            break

        if matched_hitter is None:
            logging.warning(f"Pinned batter '{pin}' not found on current roster; skipping.")
            continue

        pinned[matched_hitter["name"]] = matched_hitter["id"]

    return pinned

def select_top_batters(hitters, pin_names=None, top_n=None):
    """
    Select which hitters to feature: pinned names are always included,
    remaining slots up to top_n are filled by descending plate appearances.
    hitters: list of {"name": str, "id": str, "pa": int}
    pin_names: list of raw names to force-include (defaults to PIN_BATTERS)
    top_n: total number of batters to return (defaults to TOP_N)
    Returns: dict {name: id}
    """
    pin_names = PIN_BATTERS if pin_names is None else pin_names
    top_n = TOP_N if top_n is None else top_n

    selected = match_pins(hitters, pin_names)
    pinned_ids = set(selected.values())

    remaining = [h for h in hitters if h["id"] not in pinned_ids]
    remaining.sort(key=lambda h: h["pa"], reverse=True)

    slots_left = max(0, top_n - len(selected))
    for h in remaining[:slots_left]:
        selected[h["name"]] = h["id"]

    return selected

def build_hitter_records(roster_entries, stats_by_id):
    """
    Build hitter records from raw MLB Stats API roster entries and a
    plate-appearances lookup, excluding pitchers.
    roster_entries: the 'roster' list from the MLB Stats API roster response
    stats_by_id: dict {str(player_id): int plateAppearances}; a missing id
      is treated as 0 plate appearances (e.g. a stats fetch that partially failed)
    Returns: list of {"name": str, "id": str, "pa": int}
    """
    hitters = []
    for entry in roster_entries:
        try:
            if entry["position"]["abbreviation"] == "P":
                continue
            player_id = str(entry["person"]["id"])
            player_name = format_player_name(entry["person"]["fullName"])
            pa = stats_by_id.get(player_id, 0)
            hitters.append({"name": player_name, "id": player_id, "pa": pa})
        except Exception as e:
            logging.warning(
                f"Skipping roster entry {(entry.get('person') or {}).get('id', 'unknown')}: {str(e)}"
            )
            continue
    return hitters

def fetch_player_ids():
    """
    Fetch the Brewers active roster from the MLB Stats API to get all player IDs.
    Baseball Savant's team roster page is now client-rendered and no longer exposes
    player rows in the static HTML, so we source IDs from MLB's official API instead
    (MLBAM player IDs are shared between both systems).
    Uses the current year dynamically to ensure we're getting the current roster.
    """
    logging.info(f"Fetching player IDs from MLB Stats API roster for {CURRENT_YEAR} season.")
    # Use the 40-man roster (not just the active roster) so players on the
    # injured list, like a batter on a 10-day IL stint, are still included.
    roster_url = f'https://statsapi.mlb.com/api/v1/teams/{config.TEAM_ID}/roster?rosterType=40Man&season={CURRENT_YEAR}'
    logging.info(f"Making request to: {roster_url}")

    try:
        response = None
        for attempt in range(1, 4):
            response = requests.get(roster_url, headers=headers)
            logging.info(f"Response status code (attempt {attempt}): {response.status_code}")
            if response.status_code == 200:
                break
            logging.warning(f"Attempt {attempt} failed with status {response.status_code}. Retrying in {attempt * 10}s...")
            time.sleep(attempt * 10)

        if response.status_code != 200:
            logging.error(f"Failed to fetch roster after 3 attempts. Status code: {response.status_code}")
            logging.error(f"Response content: {response.text[:500]}")
            return {}

        logging.info("Successfully fetched roster")
        roster = response.json().get('roster', [])
        logging.info(f"Found {len(roster)} roster entries")

        # Create dictionary mapping player names to IDs
        player_lookup = {}
        for entry in roster:
            try:
                player_id = str(entry['person']['id'])
                player_name_raw = entry['person']['fullName']
                # Format to "First Last" then filter by allowlist
                formatted_name = format_player_name(player_name_raw)
                normalized = normalize_name(formatted_name)
                # Apply corrections map before comparison
                normalized = NAME_CORRECTIONS.get(normalized, normalized)
                # Check allowlist: require last name exact match and loose first-name prefix match
                if normalized not in ALLOWED_NORMALIZED:
                    # try prefix match on first name with exact last name
                    # split to first/last for both candidate and allowed
                    cand_tokens = normalized.split()
                    if len(cand_tokens) >= 2:
                        cand_first = " ".join(cand_tokens[:-1])
                        cand_last = cand_tokens[-1]
                        matched = False
                        for allowed in ALLOWED_NORMALIZED:
                            a_tokens = allowed.split()
                            if len(a_tokens) >= 2:
                                a_first = " ".join(a_tokens[:-1])
                                a_last = a_tokens[-1]
                                if cand_last == a_last and (cand_first.startswith(a_first) or a_first.startswith(cand_first)):
                                    matched = True
                                    break
                        if not matched:
                            continue
                    else:
                        continue
                player_lookup[formatted_name] = player_id
                logging.debug(f"Added allowed player: {formatted_name} (ID: {player_id})")
            except Exception as e:
                logging.warning(f"Skipping roster entry {entry.get('person', {}).get('id', 'unknown')}: {str(e)}")
                continue

        logging.info(f"Successfully created lookup for {len(player_lookup)} players")
        return player_lookup

    except Exception as e:
        logging.error(f"Error in fetch_player_ids: {str(e)}")
        logging.error(f"Response object: {response if 'response' in locals() else 'No response object'}")
        return {}

def fetch_player_xwoba(player_name, player_id):
    """Fetch xwOBA data for a specific player."""
    logging.info(f"Fetching xwOBA data for {player_name} (ID: {player_id})...")
    
    params = {
        'playerId': player_id,
        'playerType': 'Y',
    }
    
    try:
        response = requests.get('https://baseballsavant.mlb.com/player-services/rolling-thumb', 
                              params=params, 
                              headers=headers)
        logging.info(f"Response status code for {player_name}: {response.status_code}")
        
        if response.status_code != 200:
            logging.error(f"Failed to fetch data for {player_name}. Status code: {response.status_code}")
            logging.error(f"Response content: {response.text[:500]}")
            return None
            
        player_data = response.json()
        if 'plate100' not in player_data:
            logging.warning(f"No plate100 data found for {player_name} - likely a pitcher")
            return None
            
        player_data_list = player_data['plate100']
        if not player_data_list:
            logging.warning(f"No data in plate100 for {player_name}")
            return None
            
        player_df = pd.DataFrame(player_data_list)
        
        # Check if xwoba column exists
        if 'xwoba' not in player_df.columns:
            logging.warning(f"No xwoba data for {player_name}")
            return None
            
        # Convert max_game_date from UTC to Pacific Time
        if 'max_game_date' in player_df.columns:
            player_df['max_game_date'] = pd.to_datetime(player_df['max_game_date'])
            player_df['max_game_date'] = player_df['max_game_date'].dt.tz_convert('America/Chicago')
            # Format the date for better readability
            player_df['max_game_date'] = player_df['max_game_date'].dt.strftime('%Y-%m-%d %H:%M:%S %Z')
            
        player_df['xwoba'] = player_df['xwoba'].astype(float)
        # Display name as "First Last"
        player_df['player_name'] = player_name
        player_df['player_id'] = player_id
        
        logging.info(f"Successfully processed data for {player_name}")
        return player_df
        
    except Exception as e:
        logging.error(f"Error fetching data for {player_name}: {str(e)}")
        logging.error(f"Response object: {response if 'response' in locals() else 'No response object'}")
        return None

def fetch_league_average_xwoba(year=None):
    """
    Fetches the league average xwOBA from the rolling leaderboard on Baseball Savant.
    It finds the inline script data, parses it, and averages the xwOBA for all batters.
    """
    logging.info("Fetching league average xwOBA from rolling leaderboard.")
    url = 'https://baseballsavant.mlb.com/leaderboard/rolling'
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching URL: {e}")
        return None

    soup = BeautifulSoup(response.text, 'html.parser')

    script_tags = soup.find_all('script')
    
    data = None
    for script in script_tags:
        if script.string and 'var rolling =' in script.string:
            script_content = script.string
            match = re.search(r'var rolling = (\{.*?\});', script_content, re.DOTALL)
            if match:
                json_data_str = match.group(1)
                try:
                    data = json.loads(json_data_str)
                    break 
                except json.JSONDecodeError:
                    continue 

    if data is None:
        logging.error("Could not find and parse rolling data from any script tag.")
        return None

    if 'Batter100' not in data:
        logging.error("Could not find 'Batter100' key in the data.")
        return None

    player_data = data['Batter100']

    if not player_data:
        logging.warning("No player data found under 'Batter100'.")
        return None

    df = pd.DataFrame(player_data)
    xwoba_column = 'last_x_xwoba'

    if xwoba_column not in df.columns:
        logging.error(f"Could not find '{xwoba_column}' column in the player data.")
        return None

    df[xwoba_column] = pd.to_numeric(df[xwoba_column], errors='coerce')
    df.dropna(subset=[xwoba_column], inplace=True)

    average_xwoba = df[xwoba_column].mean()
    logging.info(f"Calculated league average xwOBA: {average_xwoba:.3f}")
    
    return average_xwoba

def main():
    try:
        logging.info(f"Starting xwOBA data collection for {CURRENT_YEAR} season")
        os.makedirs(output_dir, exist_ok=True)
        logging.info("Output directory checked/created.")

        # Get league average xwOBA
        lg_avg_xwoba = fetch_league_average_xwoba()
        if lg_avg_xwoba is None:
            logging.error("Failed to fetch league average xwOBA. Exiting.")
            sys.exit(1)

        # Get all player IDs
        player_lookup = fetch_player_ids()
        if not player_lookup:
            logging.error("No players found in lookup. Exiting.")
            sys.exit(1)
            
        logging.info(f"Player lookup contains {len(player_lookup)} players")
        
        # Save the player lookup
        with open(f'{output_dir}/player_lookup.json', 'w') as f:
            json.dump(player_lookup, f, indent=2)
        logging.info("Saved player lookup to JSON file")
        
        # Fetch xwOBA data for each player
        all_player_data = []
        for player_name, player_id in player_lookup.items():
            player_df = fetch_player_xwoba(player_name, player_id)
            if player_df is not None:
                # Add league average column to each player's data
                player_df['league_avg_xwoba'] = lg_avg_xwoba
                all_player_data.append(player_df)
                logging.info(f"Added data for {player_name} to collection")
            time.sleep(1)  # Be nice to the server
        
        # Combine all player data
        if all_player_data:
            df = pd.concat(all_player_data, ignore_index=True)
            logging.info(f"Combined data for {len(all_player_data)} players")
            
            # Calculate forward rank, preserving original ordering
            # In Baseball Savant data, rn=1 is already the most recent plate appearance, 
            # and rn=50 is the oldest, so we'll keep this ordering
            df["rn_fwd"] = df["rn"]
            
            # Add a debugging log to show the range of rn values
            min_rn = df["rn"].min()
            max_rn = df["rn"].max()
            logging.info(f"Source data rn values range from {min_rn} (most recent) to {max_rn} (oldest)")
            
            # Validate ordering assumption if date information is available
            if 'max_game_date' in df.columns:
                # Get a sample player with multiple records
                sample_player = df['player_name'].value_counts().idxmax()
                sample_df = df[df['player_name'] == sample_player].sort_values('rn')
                
                logging.info(f"Validating chronological order using {sample_player}'s data:")
                for idx, row in sample_df.head(3).iterrows():
                    logging.info(f"  rn={row['rn']}, date={row.get('max_game_date', 'N/A')}")
                    
                logging.info("If dates for lower rn values are more recent, the ordering is correct")
            
            # Save league average separately
            league_avg_data = {
                'year': CURRENT_YEAR,
                'league_avg_xwoba': lg_avg_xwoba,
                'timestamp': pd.Timestamp.now().isoformat()
            }
            with open(f'{output_dir}/league_avg_xwoba.json', 'w') as f:
                json.dump(league_avg_data, f, indent=2)
            
            df.drop(columns=['savant_batter_id'], inplace=True)
            # Save to various formats
            df.to_csv(csv_file, index=False)
            df.to_json(json_file, orient="records", indent=2)
            df.to_parquet(parquet_file, index=False)
            logging.info("Data written to JSON, CSV, and Parquet files.")
            
            # Upload to S3
            s3.Bucket(s3_bucket).upload_file(csv_file, s3_key_csv)
            s3.Bucket(s3_bucket).upload_file(json_file, s3_key_json)
            s3.Bucket(s3_bucket).upload_file(parquet_file, s3_key_parquet)
            s3.Bucket(s3_bucket).upload_file(
                f'{output_dir}/league_avg_xwoba.json',
                'mkebrewers/data/batting/league_avg_xwoba.json'
            )
            logging.info("Files successfully uploaded to S3.")
        else:
            logging.error("No data was collected from any players.")
            sys.exit(1)

    except Exception as e:
        logging.error(f"An error occurred: {str(e)}")
        logging.error(f"Error type: {type(e).__name__}")
        import traceback
        logging.error(f"Traceback: {traceback.format_exc()}")
        sys.exit(1)

if __name__ == "__main__":
    main()