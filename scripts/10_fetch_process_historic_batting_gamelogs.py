#!/usr/bin/env python
# coding: utf-8

"""
Boston Red Sox cumulative batting statistics by season, 1901-present
Fetches game-by-game cumulative totals for hits, doubles, home runs, walks,
strikeouts and other statistics from Baseball Reference, looping through all years.
"""

import os
import time
import boto3
import datetime
import logging
import pandas as pd
from io import BytesIO
from scripts import config

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

is_github_actions = os.getenv('GITHUB_ACTIONS') == 'true'

aws_key_id = os.environ.get("AWS_ACCESS_KEY_ID")
aws_secret_key = os.environ.get("AWS_SECRET_ACCESS_KEY")
aws_region = "us-west-1"

if is_github_actions:
    session = boto3.Session(
        aws_access_key_id=aws_key_id,
        aws_secret_access_key=aws_secret_key,
        region_name=aws_region
    )
else:
    session = boto3.Session(profile_name="haekeo", region_name=aws_region)

s3_resource = session.resource("s3")

base_dir = os.getcwd()
data_dir = os.path.join(base_dir, 'data', 'batting', 'archive')

START_YEAR = 1901
current_year = datetime.date.today().year
END_YEAR = current_year  # will fall back gracefully if no data for current year

val_cols = [
    "gtm", "pa", "ab", "r", "h", "2b", "3b", "hr", "rbi",
    "bb", "ibb", "so", "hbp", "sh", "sf", "roe", "gdp", "sb", "cs"
]
drop_cols = [
    "rk", "date", "unnamed: 3", "opp", "rslt", "ba", "obp", "slg",
    "ops", "lob", "#", "thr", "opp. starter (gmesc)"
]


def fetch_year(year):
    url = f"https://www.baseball-reference.com/teams/tgl.cgi?team={config.TEAM_ID_BBREF}&t=b&year={year}"
    try:
        df = pd.read_html(url)[0].assign(year=year)
    except (ValueError, IndexError):
        logging.warning(f"No batting data for {year}, skipping.")
        return None

    df.columns = df.columns.droplevel(0)
    df.columns = df.columns.str.lower()
    df = df.rename(columns={'': 'year'})
    df = df[pd.to_numeric(df['gtm'], errors='coerce').notna()].copy()

    df["game_date"] = pd.to_datetime(
        df["date"] + " " + df["year"].astype(str),
        format="%b %d %Y",
        errors="coerce"
    ).dt.strftime("%Y-%m-%d")

    cols_to_drop = [c for c in drop_cols if c in df.columns]
    df = df.drop(cols_to_drop, axis=1)

    existing_val_cols = [c for c in val_cols if c in df.columns]
    df[existing_val_cols] = df[existing_val_cols].fillna(0).astype(int)

    for col in existing_val_cols:
        df[f"{col}_cum"] = df.groupby("year")[col].cumsum()

    if 'gtm_cum' in df.columns:
        df = df.drop("gtm_cum", axis=1)

    return df


all_years = []
for yr in range(START_YEAR, END_YEAR + 1):
    logging.info(f"Fetching batting gamelogs for {yr}...")
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

cum_cols = ["r_cum", "h_cum", "2b_cum", "bb_cum", "so_cum", "hr_cum"]
existing_cum_cols = [c for c in cum_cols if c in df.columns]
optimized_df = df[["gtm", "year"] + existing_cum_cols].copy()

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
                df.to_parquet(buffer, index=False)
                content_type = "application/octet-stream"
            buffer.seek(0)
            s3_resource.Bucket(s3_bucket).put_object(
                Key=f"{base_path}.{fmt}", Body=buffer, ContentType=content_type
            )
            logging.info(f"Uploaded {fmt} to {s3_bucket}/{base_path}.{fmt}")
        except Exception as e:
            logging.error(f"Failed to upload {fmt} to S3: {e}")


formats = ["csv", "json", "parquet"]
file_path = os.path.join(data_dir, 'redsox_historic_batting_gamelogs')
save_dataframe(optimized_df, file_path, formats)
save_to_s3(optimized_df, "redsox/data/batting/archive/redsox_historic_batting_gamelogs", "redsox-data", formats)
