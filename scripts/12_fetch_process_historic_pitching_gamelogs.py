#!/usr/bin/env python
# coding: utf-8

# Milwaukee Brewers pitching logs by season, 1970-present
# Fetches game-by-game cumulative totals for strikeouts, hits allowed, ERA, etc.
# from Baseball Reference, looping through all years.

import os
import time
import datetime
import logging
import pandas as pd
from io import BytesIO
import boto3
from scripts import config

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

is_github_actions = os.getenv('GITHUB_ACTIONS') == 'true'

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

s3_resource = session.resource("s3")

base_dir = os.getcwd()
data_dir = os.path.join(base_dir, 'data', 'pitching')

headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36",
}

START_YEAR = 1970
# Use last completed season (current year during season, previous year in off-season)
current_year = datetime.date.today().year
END_YEAR = current_year  # will fall back if no data available

keep_cols = ['gtm', 'year', 'game_date', 'h', 'hr', 'er', 'so', 'era']


def fetch_year(year):
    url = f"https://www.baseball-reference.com/teams/tgl.cgi?team={config.TEAM_ID_BBREF}&t=p&year={year}"
    try:
        src = pd.read_html(url)[0].assign(year=year)
    except (ValueError, IndexError):
        logging.warning(f"No pitching data for {year}, skipping.")
        return None

    src.columns = src.columns.droplevel(0)
    src.columns = src.columns.str.lower()
    src = src.rename(columns={'': 'year'})
    src = src[pd.to_numeric(src['gtm'], errors='coerce').notna()].copy()

    src["game_date"] = pd.to_datetime(
        src["date"] + " " + src["year"].astype(str),
        format="%b %d %Y",
        errors="coerce"
    ).dt.strftime("%Y-%m-%d")

    available = [c for c in keep_cols if c in src.columns]
    df = src[available].copy()

    int_cols = [c for c in ["gtm", "h", "hr", "er", "so"] if c in df.columns]
    df[int_cols] = df[int_cols].fillna(0).astype(int)
    if 'era' in df.columns:
        df['era'] = pd.to_numeric(df['era'], errors='coerce')
    df['era_cum'] = df['era']

    for col in [c for c in ['h', 'hr', 'er', 'so'] if c in df.columns]:
        df[f"{col}_cum"] = df.groupby("year")[col].cumsum()

    df['year'] = pd.to_numeric(df['year'], errors='coerce').fillna(0).astype(int)
    df['gtm'] = pd.to_numeric(df['gtm'], errors='coerce').fillna(0).astype(int)

    return df


all_years = []
for yr in range(START_YEAR, END_YEAR + 1):
    logging.info(f"Fetching pitching gamelogs for {yr}...")
    df_year = fetch_year(yr)
    if df_year is not None:
        all_years.append(df_year)
    time.sleep(4)  # be polite to Baseball Reference

if not all_years:
    logging.error("No data fetched. Exiting.")
    raise SystemExit(1)

df = (
    pd.concat(all_years, ignore_index=True)
    .sort_values(["year", "gtm"], ascending=[False, True])
    .reset_index(drop=True)
)

optimized_df = df[['gtm', 'year', 'game_date', 'era_cum', 'h_cum', 'hr_cum', 'er_cum', 'so_cum']].copy()

for c in ['h_cum', 'hr_cum', 'er_cum', 'so_cum']:
    if c in optimized_df.columns:
        optimized_df[c] = pd.to_numeric(optimized_df[c], errors='coerce').fillna(0).astype(int)
optimized_df['era_cum'] = pd.to_numeric(optimized_df['era_cum'], errors='coerce')
optimized_df['game_date'] = optimized_df['game_date'].astype(str)
optimized_df['year'] = optimized_df['year'].astype(int)
optimized_df['gtm'] = optimized_df['gtm'].astype(int)

logging.info(f"Combined {len(optimized_df)} rows across {optimized_df['year'].nunique()} seasons.")


def save_dataframe(df, path_without_extension, formats):
    os.makedirs(os.path.dirname(path_without_extension), exist_ok=True)
    for file_format in formats:
        try:
            full_path = f"{path_without_extension}.{file_format}"
            if file_format == "csv":
                df.to_csv(full_path, index=False)
            elif file_format == "json":
                df.to_json(full_path, indent=4, orient="records", lines=False)
            elif file_format == "parquet":
                df.to_parquet(full_path, index=False)
            logging.info(f"Saved {file_format} to {full_path}")
        except Exception as e:
            logging.error(f"Failed to save {file_format}: {e}")


def save_to_s3(df, base_path, s3_bucket, formats):
    for fmt in formats:
        try:
            buffer = BytesIO()
            if fmt == "csv":
                df.to_csv(buffer, index=False)
                content_type = "text/csv"
            elif fmt == "json":
                df.to_json(buffer, indent=4, orient="records", lines=False)
                content_type = "application/json"
            elif fmt == "parquet":
                df.to_parquet(buffer, index=False, engine="pyarrow")
                content_type = "application/octet-stream"
            buffer.seek(0)
            s3_resource.Bucket(s3_bucket).put_object(
                Key=f"{base_path}.{fmt}", Body=buffer, ContentType=content_type
            )
            logging.info(f"Uploaded {fmt} to {s3_bucket}/{base_path}.{fmt}")
        except Exception as e:
            logging.error(f"Failed to upload {fmt} to S3: {e}")


formats = ["csv", "json", "parquet"]
file_path = os.path.join(data_dir, 'brewers_historic_pitching_gamelogs_1970-present')
save_dataframe(optimized_df, file_path, formats)
save_to_s3(optimized_df, "mkebrewers/data/pitching/brewers_historic_pitching_gamelogs_1970-present", "mkebrewers-data", formats)
