# Brewers Team Tracker

This repository — a growing work in progress — feeds [Brewers Data Bot](https://mkebrewersdata.bot), a statistical dashboard about the Milwaukee Brewers's performance. It is a fork of [Matt Stiles](https://mattstiles.me/)' incredible [Dodgers Data Bot](https://dodgersdata.bot/).

The code executes an automated workflow to fetch, process and store the team's current standings along with historical game-by-game records dating back to 1970. It also collects batting and pitching data, among other statistics, for the same period. These records are processed and used to bake out the site using the Jekyll static site generator, in concert with Github Pages, and D3.js for charts. 

The data is sourced from the heroes at [Baseball Reference](https://www.baseball-reference.com/teams/MIL/2025-schedule-scores.shtml) and [Baseball Savant](https://baseballsavant.mlb.com/) and consolidated into unified datasets for analysis and visualization purposes only. The resulting site is a non-commercial fan project.

## Automated Bluesky Posts

In addition to the data processing scripts, the repository contains scripts that generate and post daily updates to Bluesky at [@mkebrewers-bot.bsky.social](https://bsky.app/profile/mkebrewers-bot.bsky.social).

- **Daily summaries**: The `scripts/23_post_daily_summaries.py` script fetches the latest team summary data and posts about the team's overall performance, batting and pitching statistics. This is automated by the `.github/workflows/post_summaries.yml` workflow, which runs at different times throughout the day (3pm, 5pm, 7pm, 9pm, 11pm ET) to provide timely updates.
- **Lineup and pitching matchup**: The `scripts/17_fetch_lineup.py` script fetches the daily starting lineup and posts the pitching matchup once it's announced. This is automated by the `.github/workflows/tweet_lineup.yml` workflow, which checks hourly from 8am-7pm ET.
- **News roundup**: The `scripts/24_fetch_news.py` script fetches the top Brewers-related headlines and posts them. This is automated by the `.github/workflows/post_news.yml` workflow.
- **Transactions**: The `scripts/26_post_transactions.py` script posts about roster transactions. This is automated by the `.github/workflows/post_transactions.yml` workflow.

All posts include a character limit check (300 characters for Bluesky) and use S3 to track which updates have already been posted to avoid duplicates.

## How it works

The repository includes numerous Python scripts that perform the following daily operations for team standings, pitching and batting, by season. Most scripts use `scripts/config.py` for centralized configuration.

### Scripts:

- **League standings (reference for rankings):** `scripts/00_fetch_league_standings.py`
- **Update Savant boxscores archive (discovers new games, fetches only new finals):** `scripts/02_update_boxscores_archive.py`
- **League ranks (scraped):** `scripts/03_scrape_league_ranks.py`
- **Latest and historical standings:** `scripts/04_fetch_process_standings.py`
- **Team batting (figures and league ranks):** `scripts/05_fetch_process_batting.py`
- **Team pitching (figures and league ranks):** `scripts/06_fetch_process_pitching.py`
- **Dashboard summary statistics:** `scripts/07_create_toplines_summary.py`
- **Team post-season history:** `scripts/08_fetch_process_season_outcomes.py`
- **Run differential for current season (from Savant boxscores):** `scripts/09_build_wins_losses_from_boxscores.py`
- **Past/present team batting performance:** `scripts/10_fetch_process_historic_batting_gamelogs.py`
- **Team attendance (all teams):** `scripts/11_fetch_process_attendance.py`
- **Past/present team pitching performance:** `scripts/12_fetch_process_historic_pitching_gamelogs.py`
- **Team schedule:** `scripts/13_fetch_process_schedule.py`
- **MLB batting (league-level tables):** `scripts/14_fetch_process_batting_mlb.py`
- **xwOBA rolling windows (current season):** `scripts/15_fetch_xwoba.py`
- **Roster:** `scripts/19_fetch_roster.py`
- **Game pitch-by-pitch:** `scripts/20_fetch_game_pitches.py`
- **Pitch summaries:** `scripts/21_summarize_pitch_data.py`
- **Umpires:** `scripts/27_collect_umpires.py`
- **Postseason Stats:** `scripts/28_fetch_postseason_stats.py`
- **Historical Standings Fetcher:** `scripts/29_fetch_historical_standings.py`
  
Separate tweet/automation scripts are documented in the sections below (lineups, daily summaries, news, etc.).

### What they do:

1. **Fetch current season, batting and pitching data**: Download the current season's game-by-game standings for the Milwaukee Brewers from [Baseball Reference](https://www.baseball-reference.com/teams/MIL/2025-schedule-scores.shtml). The latest season's batting statitics for each player also fetched, as are the latest season's pitching statistics for each pitcher and the team as a whole.
2. **Process data**: Cleans and formats the fetched standings and batting data for consistency with the historical dataset.
3. **Concatenate with historic data**: Merges the current season's data for batting and standings with pre-existing datasets containing records for the 1970 to present seasons.
4. **Save and export data**: Outputs the combined datasets in CSV, JSON and Parquet formats.
5. **Upload to AWS S3**: Uploads the files to an AWS S3 bucket for use and archiving.

## GitHub Actions workflow

The repository uses GitHub Actions to automate the execution of the scripts each day, ensuring the datasets remains up-to-date throughout the baseball season. The key workflows include:

- **`fetch.yml`**: This is the main data pipeline, running every 30 minutes during the season. It executes all the Python scripts responsible for fetching, processing, and saving the core team and player statistics needed to build the site. Deploys the updated site to GitHub Pages.
- **`post_summaries.yml`**: Posts statistical summaries to Bluesky at scheduled times (3pm, 5pm, 7pm, 9pm, 11pm ET).
- **`tweet_lineup.yml`**: Checks hourly for the day's lineup and posts the pitching matchup to Bluesky once available (8am-7pm ET).
- **`post_news.yml`**: Fetches and posts a news roundup to Bluesky daily at 6pm ET.
- **`post_transactions.yml`**: Posts roster transactions to Bluesky daily at 2pm ET.

## Configuration and usage

To utilize this repository for your own tracking or analysis on the Brewers or another team, follow these steps:

1. **Fork the repository**: Create a copy of this repository under your own GitHub account.
2. **Configure secrets**: Add the following secrets to your repository settings for secure AWS S3 uploads (optional):
    - `AWS_ACCESS_KEY_ID`: Your AWS Access Key ID.
    - `AWS_SECRET_ACCESS_KEY`: Your AWS Secret Access Key.
3. **Adjust the scripts (Optional)**: Modify `scripts/config.py` to change team identifiers if adapting for another team.
4. **Monitor actions**: Check the "Actions" tab in your GitHub repository to see the workflow executions and ensure data is being updated as expected.

## AWS S3 Storage Setup

The project uses AWS S3 to store and serve processed data files. Here's how to set it up:

### Step 1: Create an S3 Bucket

1. Log into the [AWS Console](https://console.aws.amazon.com/)
2. Navigate to **S3** service
3. Click **Create bucket**
4. Choose a bucket name (e.g., `mkebrewers-data` or `your-domain.com`)
5. Select your preferred **region** (e.g., `us-west-1`)
6. **Uncheck** "Block all public access" (data files need to be publicly readable)
7. Acknowledge the warning about public access
8. Click **Create bucket**

### Step 2: Configure Bucket Policy

Add a bucket policy to allow public read access to your data files:

1. Go to your bucket → **Permissions** tab → **Bucket Policy**
2. Add this policy (replace `your-bucket-name` and adjust the path prefix):

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "PublicReadGetObject",
            "Effect": "Allow",
            "Principal": "*",
            "Action": "s3:GetObject",
            "Resource": "arn:aws:s3:::your-bucket-name/mkebrewers/*"
        }
    ]
}
```

### Step 3: Create IAM User for GitHub Actions

1. Navigate to **IAM** service → **Users** → **Add users**
2. Username: `github-actions-mkebrewers-data` (or similar)
3. Select **Access key - Programmatic access**
4. Click **Next: Permissions**
5. Click **Attach existing policies directly**
6. Search for and select **AmazonS3FullAccess** (or create a custom policy with write access to your bucket)
7. Click through to **Create user**
8. **Save the Access Key ID and Secret Access Key** — you'll need these for GitHub Secrets

### Step 4: Update Script Configuration

All scripts use `scripts/config.py` for S3 configuration. Verify these settings:

- `S3_BUCKET`: Your bucket name (e.g., `"mkebrewers-data"`)
- `S3_PREFIX`: Path prefix for Brewers data (e.g., `"mkebrewers"`)
- `AWS_REGION`: Your bucket's region (e.g., `"us-west-1"`)

## Web Hosting Configuration

### Recommended: GitHub Pages (FREE)

The easiest and most cost-effective hosting solution. Already configured in this repository!

**Setup Steps:**

1. Go to **Repository Settings** → **Pages**
2. Under **Source**, select **Deploy from a branch**
3. Choose branch: **gh-pages**
4. Click **Save**
5. Your site will be available at: `https://yourusername.github.io/mkebrewers-data/`

**Custom Domain (Optional):**
- Add a `CNAME` file to the root with your domain (already done: `mkebrewersdata.bot`)
- Configure DNS (see Domain Setup section below)
- Enable **Enforce HTTPS** in Pages settings

**Advantages:**
- ✅ Free hosting and bandwidth
- ✅ Automatic SSL/HTTPS certificates
- ✅ Integrated with your repo
- ✅ Auto-deploys on push to `gh-pages` branch

### Alternative: AWS S3 + CloudFront

For more control or higher traffic:

1. **Enable static website hosting** on your S3 bucket
2. Create a **CloudFront distribution** pointing to the S3 bucket
3. Configure **SSL certificate** via AWS Certificate Manager
4. Point your domain to the CloudFront distribution

### Alternative: Netlify or Vercel

Both platforms offer:
- One-click Jekyll deployment
- Automatic HTTPS
- Global CDN
- Free tier suitable for this project

## Domain Setup

If you're using a custom domain like `mkebrewersdata.bot`:

### DNS Configuration

Add these **A records** to your domain's DNS settings (for GitHub Pages):

```
Type    Name    Value
A       @       185.199.108.153
A       @       185.199.109.153
A       @       185.199.110.153
A       @       185.199.111.153
```

Add a **CNAME record** for the `www` subdomain:

```
Type    Name    Value
CNAME   www     yourusername.github.io
```

### Verification Steps

1. After updating DNS, wait 5-60 minutes for propagation
2. Test with: `dig mkebrewersdata.bot +short` (should show GitHub Pages IPs)
3. Visit your domain in a browser
4. In GitHub Pages settings, verify custom domain and enable **Enforce HTTPS**

### HTTPS Setup

GitHub Pages automatically provisions SSL certificates for custom domains via Let's Encrypt. This can take a few minutes after DNS propagates.

## Security & Secrets Setup

The project requires these secrets to be configured in GitHub repository settings:

### Required Secrets

| Secret Name | Description | How to Obtain | Required For |
|------------|-------------|---------------|--------------|
| `AWS_ACCESS_KEY_ID` | AWS IAM user access key | Created in IAM setup (see AWS S3 section) | Data uploads to S3 |
| `AWS_SECRET_ACCESS_KEY` | AWS IAM user secret key | Created in IAM setup (see AWS S3 section) | Data uploads to S3 |
| `BLUESKY_HANDLE` | Bluesky account handle | Your Bluesky handle (e.g., `mkebrewers-bot.bsky.social`) | Automated Bluesky posts |
| `BLUESKY_APP_PASSWORD` | Bluesky app-specific password | Generate at [bsky.app/settings/app-passwords](https://bsky.app/settings/app-passwords) | Automated Bluesky posts |

**Important:** `BLUESKY_APP_PASSWORD` is NOT your account password. Generate a new app password specifically for this bot in your Bluesky settings.

### Adding Secrets to GitHub

1. Go to your repository on GitHub
2. Click **Settings** → **Secrets and variables** → **Actions**
3. Click **New repository secret**
4. Enter the **Name** and **Value**
5. Click **Add secret**
6. Repeat for each secret

### Local Development Setup

For local testing, create a `.env` file in the project root (already gitignored):

```bash
AWS_ACCESS_KEY_ID=your_access_key_here
AWS_SECRET_ACCESS_KEY=your_secret_key_here
AWS_PERSONAL_PROFILE=your_aws_profile_name
```

Load these in Python scripts with:
```python
from dotenv import load_dotenv
load_dotenv()
```

## Season Transition: Off-Season to In-Season Mode

When transitioning from off-season (showing 2025 data) to in-season mode (showing live 2026 data), follow this checklist. **Recommended timing: after the first regular season game has been played.** Several scripts scrape Baseball Reference, which typically updates by ~9 AM ET the morning after a game. Switching before games have been played will cause scripts 02 and 04 to fail due to missing data.

### Step-by-Step Transition Checklist

#### 1. Update Central Year Configuration

**File:** `scripts/config.py`

Change line 14 from:
```python
CURRENT_YEAR = 2025  # Update to 2026 when 2026 season starts
```

To:
```python
CURRENT_YEAR = 2026  # Update to 2026 when 2026 season starts
```

**What this updates automatically:**
- ✅ Batting statistics (script 05)
- ✅ Pitching statistics (script 06)
- ✅ xwOBA data (script 15)
- ✅ Umpire name collection (script 27)

#### 2. Enable In-Season Scripts in Workflow

**File:** `.github/workflows/fetch.yml`

Uncomment these scripts (around lines 67-92):

```yaml
# Change FROM (off-season):
# python scripts/00_fetch_league_standings.py
# python scripts/02_update_boxscores_archive.py
# python scripts/03_scrape_league_ranks.py
# python scripts/04_fetch_process_standings.py

# TO (in-season):
python scripts/00_fetch_league_standings.py
python scripts/02_update_boxscores_archive.py
python scripts/03_scrape_league_ranks.py
python scripts/04_fetch_process_standings.py
```

Also uncomment:
```yaml
python scripts/09_build_wins_losses_from_boxscores.py
python scripts/18_generate_projection.py
python scripts/20_fetch_game_pitches.py      # Pitch-by-pitch data
python scripts/21_summarize_pitch_data.py    # Umpire scorecards
```

**Note:** The schedule script (13) should already be enabled for spring training.

#### 3. Update Workflow Schedule (Optional)

**File:** `.github/workflows/fetch.yml`

During the season, you may want to run more frequently. Update the cron schedule (line 5):

```yaml
# Off-season (4x/day):
- cron: '0 8,12,15,23 * 3-10 *'

# In-season (6x/day for more frequent updates):
- cron: '0 6,10,14,18,22,2 * 3-10 *'
```

#### 4. Commit and Push Changes

```bash
git add scripts/config.py .github/workflows/fetch.yml
git commit -m "Switch to 2026 in-season mode

- Update CURRENT_YEAR to 2026
- Enable in-season scripts (standings, boxscores, projections)
- Enable pitch analysis and umpire scorecards

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
git push
```

#### 5. Monitor First Workflow Run

After the first game has been played (data is typically available on Baseball Reference by ~9 AM ET the next morning):
1. Go to **Actions** tab in GitHub
2. Wait for next scheduled run (or trigger manually via "Run workflow")
3. Check that all scripts complete successfully
4. Verify 2026 data files appear on S3:
   - `brewers_standings_1970_present.json`
   - `brewers_player_batting_current_table.json`
   - `brewers_pitching_top_kbb_starters.json`
   - `brewers_umpires_2026.json`

#### 6. Verify Website Updates

Check your site (mkebrewersdata.bot):
- ✅ Current standings show 2026 season
- ✅ Batting/pitching tables show 2026 stats
- ✅ Schedule shows upcoming 2026 games
- ✅ Historical charts include 2026 line (after first few games)
- ✅ Umpire scorecards populate (after ~5-10 games)

### What Happens Incrementally

These features build up automatically as the season progresses:

- **Umpire scorecards** - Start appearing after first 5-10 games (scripts 20 & 21 need pitch data)
- **Win/loss projections** - Become more accurate after ~20-30 games
- **Historical comparison lines** - 2026 line appears on charts after first game
- **League rankings** - Update daily as standings change

### Post-Season Transition (October)

When playoffs begin:

1. **Uncomment postseason section** in `index.markdown` (around line 450)
2. **Enable postseason script** (28) if not already running
3. **Archive regular season data** (optional, for backup)

### What Updates Automatically

These components adapt without manual changes:

- ✅ Most data fetching scripts (use `config.CURRENT_YEAR`)
- ✅ Cumulative stats charts (append to historical data)
- ✅ Jekyll site generation
- ✅ GitHub Pages deployment

### Troubleshooting First Run

**If workflows fail:**
- Check that Baseball Reference has 2026 data published
- Spring training games may appear before regular season
- Some stats (league ranks, projections) may not work until ~5 games played

**If data doesn't appear:**
- Verify S3 bucket has 2026 files (check AWS Console or logs)
- Check browser console for JavaScript errors
- Ensure CURRENT_YEAR is set correctly in config.py

## Operations & Maintenance

### Daily Monitoring

**Check workflow status:**
- Visit **Actions** tab in your GitHub repository
- Verify `fetch.yml` and `build_site.yml` ran successfully
- Check timestamps to ensure they ran on schedule

**Common workflow failures:**
- Baseball Reference rate limiting (wait and retry)
- Network timeouts (workflows auto-retry)
- S3 upload errors (check AWS credentials)

### Workflow Schedules

The project runs on these automated schedules:

| Workflow | Schedule | Purpose |
|----------|----------|---------|
| `fetch.yml` | Every 30 minutes during season | Fetch latest stats, rebuild data and site |
| `post_summaries.yml` | 3pm, 5pm, 7pm, 9pm, 11pm ET | Post daily summaries to Bluesky |
| `tweet_lineup.yml` | Hourly 8am-7pm ET | Post lineup/pitching matchup to Bluesky |
| `post_news.yml` | 6pm ET daily | Post news roundup to Bluesky |
| `post_transactions.yml` | Daily at 2pm ET | Post roster transactions to Bluesky |

**Note:** All Bluesky posting workflows are configured to post only once per day per type to avoid spam.

### Manual Workflow Triggers

To run a workflow manually:
1. Go to **Actions** tab
2. Select the workflow (e.g., `fetch.yml`)
3. Click **Run workflow** dropdown
4. Select branch and click **Run workflow**

### Restarting Failed Workflows

1. Click on the failed workflow run
2. Click **Re-run failed jobs** button in the top right
3. Workflows will retry with the same parameters

### Dependency Updates

**Python packages:**
```bash
pip install --upgrade -r requirements.txt
pip freeze > requirements.txt
```

**Jekyll gems:**
```bash
bundle update
```

**Monthly maintenance:**
- Review GitHub Actions usage (should stay in free tier)
- Check AWS S3 costs (typically $1-5/month for this project)
- Verify all data endpoints are accessible

### Backup Strategy

**Automatic backups:**
- All data files are version-controlled in S3
- GitHub stores full git history
- Workflows can regenerate most data from source APIs

**Manual backups (recommended quarterly):**
```bash
aws s3 sync s3://mkebrewers-data/mkebrewers ./backups/mkebrewers-$(date +%Y%m%d)
```

### Cost Monitoring

**Expected monthly costs:**
- GitHub Actions: $0 (free tier: 2,000 minutes/month)
- AWS S3 Storage: ~$1-3 (for ~10-50GB data)
- AWS S3 Requests: ~$0.50-2 (for data uploads/downloads)
- GitHub Pages: $0 (free for public repos)

**Total estimated cost: $2-5/month**

To monitor AWS costs:
1. AWS Console → **Billing Dashboard**
2. Set up **Budget Alerts** for $10/month threshold
3. Review **Cost Explorer** monthly

## Troubleshooting

### Site Not Updating

**Symptoms:** GitHub Pages site shows old data despite successful workflows

**Solutions:**
1. Check if `build_site.yml` workflow completed successfully
2. Verify Jekyll build succeeded (check Actions logs)
3. Clear browser cache and hard refresh (Cmd+Shift+R / Ctrl+F5)
4. Check if `gh-pages` branch was updated (should have recent commit)
5. Manually trigger `build_site.yml` workflow

**If data files exist but site doesn't show them:**
- Check `_data/` directory for JSON files
- Verify Jekyll frontmatter references correct data paths
- Check browser console for JavaScript errors loading data

### Twitter Posting Issues

**Note:** Twitter functionality is currently **disabled** in this repository.

**To re-enable:**
1. Add Twitter API secrets to GitHub (see Security section)
2. Uncomment schedule triggers in:
   - `.github/workflows/post_summaries.yml`
   - `.github/workflows/tweet_lineup.yml`
   - `.github/workflows/post_news.yml`
3. Test with manual workflow trigger first

**Common Twitter errors:**
- `401 Unauthorized`: Check API keys/tokens are correct
- `429 Rate Limited`: Reduce posting frequency
- `403 Forbidden`: Verify app has write permissions

### Jekyll Build Failures

**Common causes:**

1. **Invalid YAML frontmatter**
   - Check for unclosed quotes or missing colons
   - Validate with: `bundle exec jekyll build --verbose`

2. **Missing dependencies**
   ```bash
   bundle install
   gem install jekyll bundler
   ```

3. **Liquid syntax errors**
   - Check template tags are properly closed
   - Look for typos in variable names

**Debug locally:**
```bash
bundle exec jekyll serve --trace
# Visit http://localhost:4000
```

### Data Fetch Errors

**Baseball Reference timeout/rate limiting:**
- Error: `HTTPError: 429 Too Many Requests`
- Solution: Workflows have built-in retries; if persistent, reduce fetch frequency
- Temporary workaround: Wait 10-15 minutes and manually re-run workflow

**Baseball Savant errors:**
- Error: `No data found for date range`
- Solution: Game might not have final data yet; workflow will catch it next run
- Check game status at [Baseball Savant](https://baseballsavant.mlb.com/)

**S3 Upload Failures:**
```
Error: NoCredentialsError
```
- Verify `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` secrets are set
- Check IAM user has S3 write permissions
- Verify bucket name in `scripts/config.py` matches your S3 bucket

### CSS Not Loading / Colors Wrong

**Symptoms:** Site loads but styling is broken or Dodgers colors still showing

**Solutions:**
1. Clear browser cache completely
2. Verify `_sass/custom.scss` was updated with Brewers colors
3. Check `assets/css/main.scss` imports custom.scss
4. Rebuild locally: `bundle exec jekyll build`
5. Check browser console for CSS 404 errors

**If colors are wrong:**
- Search codebase for `#005a9c` (Dodgers blue) — should find none
- Brewers colors should be: `#BD3039` (red) and `#0C2340` (navy)

### Data Not Appearing in Charts

**Symptoms:** Dashboard loads but charts are empty

**Solutions:**
1. Check browser console for JavaScript errors
2. Verify data file exists: `https://mkebrewers-data.s3.amazonaws.com/mkebrewers/data/standings/brewers_standings_1970_present_optimized.json`
3. Check `assets/js/dashboard.js` points to correct data URL
4. Ensure S3 bucket policy allows public read access
5. Test data endpoint with curl:
   ```bash
   curl -I https://mkebrewers-data.s3.amazonaws.com/mkebrewers/data/standings/brewers_standings_1970_present_optimized.json
   # Should return HTTP 200
   ```

### GitHub Actions Minutes Exceeded

If you exceed the free tier (2,000 minutes/month):

1. **Reduce workflow frequency:**
   - Change `fetch.yml` from every 3 hours to every 6 hours during season
   - Disable workflows during off-season

2. **Optimize script runtime:**
   - Scripts already optimized for speed
   - Most workflows complete in 5-10 minutes

3. **Upgrade to GitHub Pro** (if needed):
   - $4/month for 3,000 minutes
   - Unlikely to be necessary for this project

## Data storage and access

The processed datasets are uploaded to an AWS S3 bucket. 

### Standings

**Latest season summary**

- [JSON](https://mkebrewers-data.s3.amazonaws.com/mkebrewers/data/standings/season_summary_latest.json)
- [CSV](https://mkebrewers-data.s3.amazonaws.com/mkebrewers/data/standings/season_summary_latest.csv)

**Game-by-game standings, 1970 to present:**

- [JSON](https://mkebrewers-data.s3.amazonaws.com/mkebrewers/data/standings/brewers_standings_1970_present.json)
- [CSV](https://mkebrewers-data.s3.amazonaws.com/mkebrewers/data/standings/brewers_standings_1970_present.csv)
- [Parquet](https://mkebrewers-data.s3.amazonaws.com/mkebrewers/data/standings/brewers_standings_1970_present.parquet)

### Batting

**Season-by-season batting statistics, by player, 1970 to present:**

- [JSON](https://mkebrewers-data.s3.amazonaws.com/mkebrewers/data/batting/brewers_player_batting_1970_present.json)
- [CSV](https://mkebrewers-data.s3.amazonaws.com/mkebrewers/data/batting/brewers_player_batting_1970_present.csv)
- [Parquet](https://mkebrewers-data.s3.amazonaws.com/mkebrewers/data/batting/brewers_player_batting_1970_present.parquet)

**Other current season player batting statistics:**
- Batting average, on-base and slugging percentage and walks, home runs and strikeouts by plate appearance via Baseball Savant.
    - [JSON](https://mkebrewers-data.s3.amazonaws.com/mkebrewers/data/batting/brewers_player_batting_current_table.json)
    - [CSV](https://mkebrewers-data.s3.amazonaws.com/mkebrewers/data/batting/brewers_player_batting_current_table.csv)
    - [Parquet](https://mkebrewers-data.s3.amazonaws.com/mkebrewers/data/batting/brewers_player_batting_current_table.parquet)

**Season-by-season batting at the team level, 1970 to present:**
- How the team ranks or ranked in the league by season
    - [JSON](https://mkebrewers-data.s3.amazonaws.com/mkebrewers/data/batting/brewers_team_batting_ranks_1970_present.json)
    - [CSV](https://mkebrewers-data.s3.amazonaws.com/mkebrewers/data/batting/brewers_team_batting_ranks_1970_present.csv)
    - [Parquet](https://mkebrewers-data.s3.amazonaws.com/mkebrewers/data/batting/brewers_team_batting_ranks_1970_present.parquet)

- Team aggregates by season for major batting stats: hits, homers, strikeouts, etc.
    - [JSON](https://mkebrewers-data.s3.amazonaws.com/mkebrewers/data/batting/brewers_team_batting_1970_present.json)
    - [CSV](https://mkebrewers-data.s3.amazonaws.com/mkebrewers/data/batting/brewers_team_batting_1970_present.csv)
    - [Parquet](https://mkebrewers-data.s3.amazonaws.com/mkebrewers/data/batting/brewers_team_batting_1970_present.parquet)

#### xwOBA (current season)

- `scripts/15_fetch_xwoba.py` fetches rolling 100 plate appearance xwOBA series per batter from Baseball Savant
- Filters to a maintained allowlist of regular batters and normalizes names to match roster output
- Writes outputs and uploads to S3
  - Current timeseries per allowed batter
    - [JSON](https://mkebrewers-data.s3.amazonaws.com/mkebrewers/data/batting/brewers_xwoba_current.json)
    - [CSV](https://mkebrewers-data.s3.amazonaws.com/mkebrewers/data/batting/brewers_xwoba_current.csv)
    - [Parquet](https://mkebrewers-data.s3.amazonaws.com/mkebrewers/data/batting/brewers_xwoba_current.parquet)
  - League average xwOBA snapshot
    - [JSON](https://mkebrewers-data.s3.amazonaws.com/mkebrewers/data/batting/league_avg_xwoba.json)

### Pitching

**Current season pitching:**
- Team aggregates for major pitching stats: runs, ERA, etc.
    - [JSON](https://mkebrewers-data.s3.amazonaws.com/mkebrewers/data/pitching/brewers_pitching_totals_current.json)
    - [CSV](https://mkebrewers-data.s3.amazonaws.com/mkebrewers/data/pitching/brewers_pitching_totals_current.csv)
    - [Parquet](https://mkebrewers-data.s3.amazonaws.com/mkebrewers/data/pitching/brewers_pitching_totals_current.parquet)

- Team's league ranking for major pitching stats: runs, ERA, etc.

    - [JSON](https://mkebrewers-data.s3.amazonaws.com/mkebrewers/data/pitching/brewers_pitching_ranks_current.json)
    - [CSV](https://mkebrewers-data.s3.amazonaws.com/mkebrewers/data/pitching/brewers_pitching_ranks_current.csv)
    - [Parquet](https://mkebrewers-data.s3.amazonaws.com/mkebrewers/data/pitching/brewers_pitching_ranks_current.parquet)

---

## Notes

This project, which started as a mere fork of the Dodgers Data Bot, will hopefully be adding some new and different features. If you have questions, [drop a line](mailto:twallac10@gmail.com). 

## Contributions

Contributions, suggestions and enhancements are welcome! Please open an issue or submit a pull request if you have suggestions for improvement. 

## License

This project is open-sourced under the MIT License. See the LICENSE file for more details.
