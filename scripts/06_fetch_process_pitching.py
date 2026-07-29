#!/usr/bin/env python
# coding: utf-8

"""
Milwaukee Brewers pitching
This script downloads the team's current pitching table from [Baseball Reference](https://www.baseball-reference.com/teams/MIL/{YEAR}-pitching.shtml#all_team_pitching) and outputs the data to CSV, JSON and Parquet formats for later analysis and visualization.
"""

# Import Python tools
import os
import re
import boto3
import pandas as pd
import requests
from io import BytesIO

"""
Fetch
"""

from scripts import config


def normalize_pitcher_name(name):
    """Lowercase and collapse whitespace for name comparison."""
    return " ".join(name.split()).lower()


def clean_br_name(name):
    """
    Strip Baseball-Reference's display annotations (trailing '*' for
    throws-left, and any trailing ' (...)' parenthetical like IL status or
    '(40-man)') to get a name comparable against the MLB Stats API roster.
    Used only for matching -- the original annotated name is never changed
    in the output.
    """
    cleaned = name.rstrip("*").strip()
    cleaned = re.sub(r"\s*\([^)]*\)\s*$", "", cleaned)
    return normalize_pitcher_name(cleaned)


def fetch_current_roster_names():
    """
    Fetch the Brewers' current 40-man roster from the MLB Stats API and
    return a set of normalized full names (pitchers and hitters both -- this
    only answers "on the roster," not "what position").
    Returns an empty set if the request fails; callers should treat an
    empty set as "skip filtering" rather than "roster is empty."
    """
    roster_url = (
        f"https://statsapi.mlb.com/api/v1/teams/{config.TEAM_ID}/roster"
        f"?rosterType=40Man&season={config.CURRENT_YEAR}"
    )
    try:
        response = requests.get(roster_url, headers={"User-Agent": "Mozilla/5.0"})
        if response.status_code != 200:
            print(f"Failed to fetch current roster for pitching filter. Status code: {response.status_code}")
            return set()
        roster = response.json().get("roster", [])
        return {normalize_pitcher_name(e["person"]["fullName"]) for e in roster}
    except Exception as e:
        print(f"Error fetching current roster for pitching filter: {e}")
        return set()


def ensure_directory_exists(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)

def save_dataframe(df, path_without_extension, formats):
    for file_format in formats:
        full_path = f"{path_without_extension}.{file_format}"
        ensure_directory_exists(full_path)
        if file_format == "csv":
            df.to_csv(full_path, index=False)
        elif file_format == "json":
            df.to_json(full_path, orient="records")
        elif file_format == "parquet":
            df.to_parquet(full_path)
        print(f"Saved {file_format} to {full_path}")

# Function to save dataframes with different formats and file extensions

def save_dataframe(df, path_without_extension, formats):
    """
    Save DataFrames in multiple formats.
    """
    for file_format in formats:
        if file_format == "csv":
            df.to_csv(f"{path_without_extension}.{file_format}", index=False)
        elif file_format == "json":
            df.to_json(
                f"{path_without_extension}.{file_format}", indent=4, orient="records"
            )
        elif file_format == "parquet":
            df.to_parquet(f"{path_without_extension}.{file_format}", index=False)
        else:
            print(f"Unsupported format: {file_format}")


def save_to_s3(df, base_path, s3_bucket, formats=["csv", "json", "parquet"], profile_name=None):
    """
    Save Pandas DataFrame in specified formats and upload to S3 bucket using a specified AWS profile.

    :param df: DataFrame to save.
    :param base_path: Base file path without format extension.
    :param s3_bucket: S3 bucket name.
    :param formats: List of formats to save -- 'csv', 'json', 'parquet'.
    :param profile_name: AWS CLI profile name to use for credentials (optional).
    """
    session = boto3.Session(
        aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
        aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
        region_name='us-east-2',
    )
    s3_resource = session.resource("s3")

    for fmt in formats:
        file_path = f"{base_path}.{fmt}"
        buffer = BytesIO()
        if fmt == "csv":
            df.to_csv(buffer, index=False)
            content_type = "text/csv"
        elif fmt == "json":
            df.to_json(buffer, orient="records", indent=2)
            content_type = "application/json"
        elif fmt == "parquet":
            df.to_parquet(buffer, index=False)
            content_type = "application/vnd.apache.parquet"

        buffer.seek(0)
        try:
            s3_resource.Bucket(s3_bucket).put_object(
                Key=file_path, Body=buffer, ContentType=content_type
            )
            print(f"Uploaded {fmt} to {s3_bucket}/{file_path}")
        except Exception as e:
            print(f"Failed to upload {fmt} to {s3_bucket}/{file_path}: {e}")


def main():
    global players

    # Pitching table url for the current season
    # Using config.CURRENT_YEAR - set to 2025 for off-season, update to 2026 when season starts
    year = str(config.CURRENT_YEAR)
    url = f"https://www.baseball-reference.com/teams/{config.TEAM_ID_BBREF}/{year}-pitching.shtml#all_team_pitching"

    """
    Team stats
    """

    summary_df = (
        pd.read_html(url)[0]
        .query(f"Rk.isna() and Rk != 'Rk'")
        .dropna(thresh=7)
        .assign(season=year)
        .rename(columns={'Player': 'name'})
    )
    summary_df.columns = summary_df.columns.str.lower()

    # Ranks
    ranks = (
        summary_df.query('name == "Rank in 15 NL teams"')
        .dropna(axis=1)
        .reset_index(drop=True)
    ).copy()


    # Totals
    totals = (
        summary_df.query('name == "Team Totals"')
        .dropna(axis=1)
        .reset_index(drop=True)
        .copy()
    )

    # Individual players - get full table
    players_df = pd.read_html(url)[0]
    players_df.columns = players_df.columns.str.lower()

    # Filter to actual players (exclude team totals, ranks, header rows)
    players = (
        players_df
        .query('rk.notna() and rk != "Rk"')
        .query('player != "Team Totals"')
        .query('~player.str.contains("Rank in", na=False)')
        .copy()
    )

    # Filter out players no longer with the organization -- Baseball-
    # Reference's season table doesn't drop a player once they've been
    # traded/released/optioned elsewhere, so cross-check against the
    # current 40-man roster instead of trusting the season-cumulative view.
    current_roster_names = fetch_current_roster_names()
    if current_roster_names:
        players = players[
            players["player"].apply(clean_br_name).isin(current_roster_names)
        ].copy()
    else:
        print("Roster fetch returned no names; skipping current-roster filter for pitching leaderboard.")

    # Convert numeric columns (including SO/BB which Baseball Reference provides)
    numeric_cols = ['era+', 'fip', 'so/bb', 'ip']
    for col in numeric_cols:
        if col in players.columns:
            players[col] = pd.to_numeric(players[col], errors='coerce')

    # Split into starters (pos == 'SP') and relievers (pos != 'SP')
    if all(col in players.columns for col in ['pos', 'ip', 'so/bb', 'era+', 'fip']):
        starters = players[players['pos'] == 'SP']
        relievers = players[players['pos'] != 'SP']

        top_starters = (
            starters[starters['ip'] >= 30]
            .nlargest(5, 'so/bb')
            [['player', 'era+', 'fip', 'so/bb']]
            .rename(columns={'player': 'name', 'so/bb': 'so_bb'})
            .reset_index(drop=True)
        )
        top_relievers = (
            relievers[relievers['ip'] >= 10]
            .nlargest(5, 'so/bb')
            [['player', 'era+', 'fip', 'so/bb']]
            .rename(columns={'player': 'name', 'so/bb': 'so_bb'})
            .reset_index(drop=True)
        )
    else:
        print(f"Available columns: {players.columns.tolist()}")
        top_starters = pd.DataFrame(columns=['name', 'era+', 'fip', 'so_bb'])
        top_relievers = pd.DataFrame(columns=['name', 'era+', 'fip', 'so_bb'])

    """
    Export
    """

    # Save local files
    formats = ["csv", "json", "parquet"]
    save_dataframe(totals, f"data/pitching/brewers_pitching_totals_current", formats)
    save_dataframe(ranks, f"data/pitching/brewers_pitching_ranks_current", formats)
    save_dataframe(top_starters, f"data/pitching/brewers_pitching_top_kbb_starters", formats)
    save_dataframe(top_relievers, f"data/pitching/brewers_pitching_top_kbb_relievers", formats)

    # Save to S3
    save_to_s3(
        totals,
        "mkebrewers/data/pitching/brewers_pitching_totals_current",
        "mkebrewers-data",
    )
    save_to_s3(
        ranks,
        "mkebrewers/data/pitching/brewers_pitching_ranks_current",
        "mkebrewers-data",
    )
    save_to_s3(
        top_starters,
        "mkebrewers/data/pitching/brewers_pitching_top_kbb_starters",
        "mkebrewers-data",
    )
    save_to_s3(
        top_relievers,
        "mkebrewers/data/pitching/brewers_pitching_top_kbb_relievers",
        "mkebrewers-data",
    )


if __name__ == "__main__":
    main()
