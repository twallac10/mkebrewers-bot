import os
import json
import boto3
from atproto import Client
import logging
import argparse
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from botocore.exceptions import ClientError
from scripts import config
import time

# Setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Environment Variables & AWS/S3
is_github_actions = os.getenv('GITHUB_ACTIONS') == 'true'
s3_bucket_name = "redsox-data"
s3_key_transactions_archive = "redsox/data/roster/redsox_transactions_archive.json"

if is_github_actions:
    session = boto3.Session(region_name="us-west-1")
else:
    profile_name = os.environ.get("AWS_PERSONAL_PROFILE", "haekeo")
    session = boto3.Session(profile_name=profile_name, region_name="us-west-1")

s3_resource = session.resource("s3")

def get_posted_transactions():
    """Reads the list of already posted transaction IDs from S3."""
    s3_key = "redsox/data/bluesky/posted_transactions.json"
    try:
        obj = s3_resource.Object(s3_bucket_name, s3_key)
        posted_data = json.loads(obj.get()['Body'].read().decode('utf-8'))
        return set(posted_data.get('transaction_ids', []))
    except ClientError as e:
        if e.response['Error']['Code'] == 'NoSuchKey':
            return set()
        raise

def add_posted_transaction(transaction_id):
    """Adds a transaction ID to the list of posted transactions in S3."""
    s3_key = "redsox/data/bluesky/posted_transactions.json"

    # Get existing posted transactions
    posted_ids = get_posted_transactions()
    posted_ids.add(transaction_id)

    # Keep only the most recent 1000 to prevent the file from growing too large
    posted_list = list(posted_ids)
    if len(posted_list) > 1000:
        posted_list = posted_list[-1000:]

    # Save back to S3
    posted_data = {"transaction_ids": posted_list}
    obj = s3_resource.Object(s3_bucket_name, s3_key)
    obj.put(Body=json.dumps(posted_data, indent=2))
    logging.info(f"Added transaction ID to posted list: {transaction_id}")

def create_transaction_id(transaction_row):
    """Creates a unique ID for a transaction based on date and transaction text."""
    # Use first 50 characters of transaction text to create a unique but manageable ID
    transaction_snippet = transaction_row['transaction'][:50].replace(' ', '_').replace(',', '').replace('.', '')
    return f"{transaction_row['date']}_{transaction_snippet}"

def post_to_bluesky(post_text, transaction_id):
    """Posts to Bluesky and marks the transaction as posted on success."""
    BLUESKY_HANDLE = os.environ.get("BLUESKY_HANDLE")
    BLUESKY_APP_PASSWORD = os.environ.get("BLUESKY_APP_PASSWORD")

    if not all([BLUESKY_HANDLE, BLUESKY_APP_PASSWORD]):
        logging.error("Bluesky credentials are not fully set. Cannot post.")
        return False

    try:
        client = Client()
        client.login(BLUESKY_HANDLE, BLUESKY_APP_PASSWORD)
        response = client.send_post(text=post_text)
        logging.info(f"Post published successfully to Bluesky: {response.uri}")
        add_posted_transaction(transaction_id)
        return True
    except Exception as e:
        logging.error(f"Failed to post to Bluesky: {e}")
        return False

def format_transaction_post(transaction_row):
    """Formats a transaction into a Bluesky post."""
    date = transaction_row['date']
    transaction_text = transaction_row['transaction']

    # Format the date nicely
    try:
        date_obj = datetime.strptime(date, '%Y-%m-%d')
        formatted_date = date_obj.strftime('%B %d, %Y')
    except:
        formatted_date = date

    # Create the post
    post_text = f"🏟️ {config.TEAM_NAME_SIMPLE} transaction ({formatted_date}):\n\n{transaction_text}"

    # Ensure post fits in character limit (300 chars for Bluesky)
    if len(post_text) > 300:
        # Truncate the transaction text if needed
        max_transaction_length = 300 - len(f"🏟️ {config.TEAM_NAME_SIMPLE} transaction ({formatted_date}):\n\n") - 3  # 3 for "..."
        truncated_transaction = transaction_text[:max_transaction_length] + "..."
        post_text = f"🏟️ {config.TEAM_NAME_SIMPLE} transaction ({formatted_date}):\n\n{truncated_transaction}"

    return post_text

def fetch_new_transactions():
    """Fetches new transactions that haven't been posted yet."""
    try:
        # Download the transaction archive from S3
        obj = s3_resource.Object(s3_bucket_name, s3_key_transactions_archive)
        transactions_data = json.loads(obj.get()['Body'].read().decode('utf-8'))

        # Get posted transaction IDs
        posted_ids = get_posted_transactions()

        # Find new transactions (not already posted)
        new_transactions = []
        for transaction in transactions_data:
            transaction_id = create_transaction_id(transaction)
            if transaction_id not in posted_ids:
                new_transactions.append(transaction)

        # Sort by date (newest first) and limit to recent ones
        new_transactions.sort(key=lambda x: x['date'], reverse=True)

        # Only consider transactions from the last 7 days to avoid posting very old ones
        # that might not have been posted due to script not running
        team_tz = ZoneInfo(config.TEAM_TIMEZONE)
        seven_days_ago_obj = datetime.now(team_tz).date() - timedelta(days=7)
        seven_days_ago = seven_days_ago_obj.strftime('%Y-%m-%d')

        recent_new_transactions = [
            t for t in new_transactions
            if t['date'] >= seven_days_ago
        ]

        return recent_new_transactions

    except Exception as e:
        logging.error(f"Error fetching transactions: {e}")
        return []

def should_post_transactions():
    """Determines if transactions should be posted based on time."""
    team_tz = ZoneInfo(config.TEAM_TIMEZONE)
    current_hour = datetime.now(team_tz).hour

    # Post transactions during reasonable hours (7 AM to 10 PM PT)
    if 7 <= current_hour <= 22:
        logging.info(f"Good time to post transactions (hour: {current_hour})")
        return True
    else:
        logging.info(f"Outside prime posting hours (hour: {current_hour}). Skipping transaction posts.")
        return False

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=f"Post new {config.TEAM_NAME_SIMPLE} transactions to Bluesky.")
    parser.add_argument("--post", action="store_true", help="Post new transactions to Bluesky.")
    parser.add_argument("--force", action="store_true", help="Force posting regardless of time constraints.")
    args = parser.parse_args()

    # Check if we should post (unless forced)
    if not args.force and not should_post_transactions():
        exit()

    # Fetch new transactions
    new_transactions = fetch_new_transactions()

    if new_transactions:
        logging.info(f"Found {len(new_transactions)} new transactions to potentially post")

        posts_made = 0
        for transaction in new_transactions:
            transaction_id = create_transaction_id(transaction)
            post_text = format_transaction_post(transaction)

            print(f"--- Transaction Post {posts_made + 1} ---")
            print(f"ID: {transaction_id}")
            print(f"Post: {post_text}")
            print()

            if args.post:
                success = post_to_bluesky(post_text, transaction_id)
                if success:
                    posts_made += 1
                    # Add a small delay between posts to be respectful to Bluesky's API
                    time.sleep(2)
            else:
                logging.info("Dry run: --post flag not provided. Not posting to Bluesky.")

        if args.post:
            logging.info(f"Successfully posted {posts_made} transaction posts to Bluesky")
    else:
        logging.info("No new transactions found to post.")
