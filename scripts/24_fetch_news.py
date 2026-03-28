import requests
from bs4 import BeautifulSoup
import json
import os
from atproto import Client
import argparse
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
import boto3
from botocore.exceptions import ClientError
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
else:
    profile_name = os.environ.get("AWS_PERSONAL_PROFILE", "haekeo")
    session = boto3.Session(profile_name=profile_name, region_name="us-west-1")

s3_resource = session.resource("s3")

def get_last_post_date(post_type):
    """Reads the last post date for a given type from S3."""
    s3_key = f"redsox/data/bluesky/last_post_date_{post_type}.txt"
    try:
        obj = s3_resource.Object(s3_bucket_name, s3_key)
        last_date_str = obj.get()['Body'].read().decode('utf-8').strip()
        return last_date_str
    except ClientError as e:
        if e.response['Error']['Code'] == 'NoSuchKey':
            return None
        raise

def set_last_post_date(date_str, post_type):
    """Writes the last post date for a given type to S3."""
    s3_key = f"redsox/data/bluesky/last_post_date_{post_type}.txt"
    obj = s3_resource.Object(s3_bucket_name, s3_key)
    obj.put(Body=date_str)
    logging.info(f"Successfully updated last post date for '{post_type}' to: {date_str}")

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
        team_tz = ZoneInfo(config.TEAM_TIMEZONE)
        today_str = datetime.now(team_tz).strftime('%Y-%m-%d')
        set_last_post_date(today_str, post_type)
    except Exception as e:
        logging.error(f"Failed to post to Bluesky: {e}")

# TODO: Add Boston Globe and other Red Sox-specific news sources.

def fetch_mlb_news():
    """
    Fetches the top story from MLB.com.
    """
    url = f"https://www.mlb.com/{config.TEAM_NAME.replace(' ', '').lower()}/news"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36'
    }
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching the URL: {e}")
        return None

    soup = BeautifulSoup(response.text, 'html.parser')

    # Find the first article item
    article_item = soup.find('li', class_='article-navigation__item')

    if not article_item:
        print("Could not find the main story on MLB.com.")
        return None

    story_data = {}

    # Extract title and URL
    headline_tag = article_item.find('span', class_='article-navigation__item__meta-headline')
    link_tag = article_item.find('a')

    if headline_tag:
        story_data['title'] = headline_tag.get_text(strip=True)
    else:
        story_data['title'] = None

    if link_tag and link_tag.has_attr('href'):
        story_data['url'] = f"https://www.mlb.com{link_tag['href']}"
    else:
        story_data['url'] = None

    # Description and time are not available in the list view
    story_data['description'] = None
    story_data['time'] = None

    story_data['source'] = 'MLB.com'
    return story_data

def format_news_post(articles):
    """Formats a list of articles into a Bluesky post."""
    post_lines = []
    for article in articles:
        if article and article.get('title') and article.get('url'):
            post_lines.append(f"- {article['source']}: {article['title']} {article['url']}")
    return "\n\n".join(post_lines)

def should_post_news():
    """Determines if news should be posted based on time and whether it's been posted today."""
    team_tz = ZoneInfo(config.TEAM_TIMEZONE)
    current_hour = datetime.now(team_tz).hour
    today_str = datetime.now(team_tz).strftime('%Y-%m-%d')

    # Check if already posted today
    last_post_date = get_last_post_date("news")
    if last_post_date == today_str:
        logging.info("News has already been posted today. Skipping.")
        return False

    # Post news during reasonable hours (8 AM to 6 PM PT)
    if 8 <= current_hour <= 18:
        logging.info(f"Good time to post news (hour: {current_hour})")
        return True
    else:
        logging.info(f"Outside prime news hours (hour: {current_hour}). Skipping news post.")
        return False

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Fetch Red Sox news and optionally post to Bluesky.")
    parser.add_argument("--post", action="store_true", help="Post the news roundup to Bluesky.")
    parser.add_argument("--force", action="store_true", help="Force posting regardless of time (still respects daily limit).")
    args = parser.parse_args()

    post_type = "news"
    team_tz = ZoneInfo(config.TEAM_TIMEZONE)
    today_str = datetime.now(team_tz).strftime('%Y-%m-%d')

    # Check if we should post (unless forced)
    if not args.force and not should_post_news():
        exit()

    articles = []

    # TODO: Add Boston Globe or other Red Sox specific sources.

    mlb_news = fetch_mlb_news()
    if mlb_news:
        articles.append(mlb_news)

    if articles:
        post_text = format_news_post(articles)
        print("--- Generated Post ---")
        print(post_text)

        if args.post:
            post_to_bluesky(post_text, post_type)
        else:
            logging.info("Dry run: --post flag not provided. Not posting to Bluesky.")
    else:
        logging.info("No articles found to post.")
