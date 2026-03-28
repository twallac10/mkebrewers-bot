# Season Transition Checklist

This guide walks through updating the Red Sox Data Bot for a new season.

## Quick Start

For most updates, use the automated script:

```bash
# Preview changes
python scripts/update_season_year.py --old-year 2025 --new-year 2026 --dry-run

# Apply changes
python scripts/update_season_year.py --old-year 2025 --new-year 2026
```

## Pre-Season Setup (Do This Before Opening Day)

### 1. Update Year References (Automated)

Run the season update script:

```bash
python scripts/update_season_year.py --old-year 2025 --new-year 2026
```

This updates:
- ✓ Postseason section headers
- ✓ Postseason data file references
- ✓ Year-over-year comparison charts
- ✓ Jekyll data fallbacks
- ✓ Pitch data download links

### 2. Verify Bluesky Credentials

Check that your Bluesky credentials are still valid:

```bash
# Test posting (won't actually post without --post flag)
python scripts/23_post_daily_summaries.py --type summary
```

If you see authentication errors, regenerate your app password at https://bsky.app/settings/app-passwords

### 3. Test Data Generation

Run a test data fetch to ensure 2026 data generation works:

```bash
# Set AWS credentials (if running locally)
export AWS_ACCESS_KEY_ID=your_key
export AWS_SECRET_ACCESS_KEY=your_secret

# Test key data scripts
python scripts/04_fetch_process_standings.py
python scripts/05_fetch_process_batting.py
python scripts/06_fetch_process_pitching.py
```

**Note:** During off-season, these will fail with "No tables found". This is expected. Once the season starts, they should work.

### 4. Review Workflow Schedules

Check that automated workflows are properly scheduled in `.github/workflows/`:

- **`fetch.yml`**: Runs every 30 minutes during season
  - Schedule: `'*/30 * * * *'` (currently enabled)
  - Fetches game data, standings, stats

- **`post_summaries.yml`**: Posts daily summaries to Bluesky
  - Schedule: `'0 15,17,19,21,23 * * *'` (3pm, 5pm, 7pm, 9pm, 11pm ET)

- **`tweet_lineup.yml`**: Posts lineup/pitching matchup
  - Schedule: `'0 12-23 * * *'` (hourly from 5am-4pm PT / 8am-7pm ET)

- **`post_news.yml`**: Posts news roundup
  - Schedule: `'0 18 * * *'` (6pm ET)

### 5. Check S3 Bucket Permissions

Verify your S3 bucket is set up for 2026 paths:

```bash
# Test S3 access
aws s3 ls s3://redsox-data/redsox/data/ --profile haekeo
```

Ensure bucket policy allows public read access to `redsox/data/*` paths.

## Opening Day Tasks

### 1. Monitor First Data Run

Watch the first automated `fetch.yml` workflow run:

1. Go to https://github.com/sogrady/redsox-bot/actions
2. Click on "Fetch and Process Red Sox Data"
3. Monitor the most recent run

Common issues:
- **"No tables found"**: Game hasn't started yet, wait
- **S3 upload errors**: Check AWS credentials in GitHub Secrets
- **Jekyll build errors**: Check for syntax errors in templates

### 2. Verify Data Files

After the first successful run, check that 2026 data files exist:

**Local files:**
```bash
ls -lh data/standings/redsox_standings_1901_present.json
ls -lh _data/standings/all_teams_standings_metrics_2026.json
```

**S3 files:**
```bash
curl -I https://redsox-data.s3.amazonaws.com/redsox/data/standings/redsox_standings_1901_present.json
```

### 3. Test the Live Site

Visit https://redsox.bot and verify:

- [ ] Final 2025 standings still show in "Final regular season standings"
- [ ] 2026 current season data starts appearing once games are played
- [ ] Charts switch from showing 2025 to 2026 as "current year"
- [ ] Cumulative stats charts load without errors
- [ ] Postseason 2025 section still shows (until you update to 2026)

### 4. Test Bluesky Posting

Wait for the first scheduled Bluesky post, then verify:

1. Check https://bsky.app/profile/redsoxbot.bsky.social
2. Verify posts are appearing with Red Sox 2026 stats
3. Check workflow runs in GitHub Actions for any errors

## During Season Maintenance

### Monitor Automated Workflows

Check GitHub Actions daily for the first week:
- All workflows should complete successfully
- Data should update every 30 minutes during games
- Bluesky posts should go out on schedule

### Manual Data Fixes

If a workflow fails, you can manually run scripts:

```bash
# Example: Manually fetch standings
python scripts/04_fetch_process_standings.py

# Example: Manually post to Bluesky
python scripts/23_post_daily_summaries.py --type summary --force
```

## Post-Season Tasks

### 1. Archive 2026 Data

After the season ends, archive the data:

```bash
# Run historical standings fetch
python scripts/29_fetch_historical_standings.py
```

### 2. Enable Postseason Section

When playoffs begin (usually early October), you need to uncomment the postseason section on the homepage:

**Step 1: Uncomment the section in index.markdown**

1. Open `index.markdown`
2. Find the commented postseason section (around line 33):
   ```html
   <!-- Postseason section commented out - uncomment when 2026 playoffs begin
   <div class="postseason-stats-section">
     <h2 class="stat-group postseason-header">Postseason 2026</h2>
     ...
   </div>
   -->
   ```
3. Remove the `<!--` and `-->` comment markers
4. Save the file

**Step 2: Copy postseason data files**

The automated workflows will generate postseason data files. Copy them to the assets directory:

```bash
cp data/postseason/redsox_postseason_stats_2026.json assets/data/postseason/
cp data/postseason/redsox_postseason_series_2026.json assets/data/postseason/
```

**Step 3: Commit and push**

```bash
git add index.markdown assets/data/postseason/
git commit -m "Enable postseason section for 2026 playoffs"
git push
```

The postseason section will now display on the homepage with playoff journey and team hitting stats.

## Troubleshooting

### Site Shows Old Season Data

The site should automatically switch to showing 2026 once data exists. If it doesn't:

1. Check browser console for JavaScript errors
2. Verify `redsox_standings_1901_present.json` includes 2026 data
3. Clear browser cache and reload

### Bluesky Posts Not Working

1. Check GitHub Secrets are set:
   - `BLUESKY_HANDLE`
   - `BLUESKY_APP_PASSWORD`

2. Test locally:
   ```bash
   export BLUESKY_HANDLE="redsoxbot.bsky.social"
   export BLUESKY_APP_PASSWORD="your-app-password"
   python scripts/23_post_daily_summaries.py --type summary
   ```

3. Check rate limits: Bluesky allows 300 posts per day

### Workflows Failing

1. Check workflow logs in GitHub Actions
2. Common fixes:
   - Re-run the workflow
   - Check AWS credentials in GitHub Secrets
   - Verify Python dependencies in requirements.txt

## Reference

### Key Files

- `scripts/update_season_year.py` - Automated year updater
- `.github/workflows/fetch.yml` - Main data fetching workflow
- `assets/js/dashboard.js` - Chart rendering (has year references)
- `index.markdown` - Main page (has postseason header)

### Important Dates

- **Pre-season**: ~2 weeks before Opening Day
- **Opening Day**: Usually late March / early April
- **Postseason**: October
- **Off-season**: November - February

### GitHub Secrets Required

| Secret | Description |
|--------|-------------|
| `AWS_ACCESS_KEY_ID` | AWS IAM user access key |
| `AWS_SECRET_ACCESS_KEY` | AWS IAM user secret key |
| `BLUESKY_HANDLE` | Bluesky handle (e.g., redsoxbot.bsky.social) |
| `BLUESKY_APP_PASSWORD` | Bluesky app password (NOT your account password) |

### Useful Commands

```bash
# Test Jekyll site locally
bundle exec jekyll serve

# Check git status
git status

# View recent commits
git log --oneline -10

# Check S3 files
aws s3 ls s3://redsox-data/redsox/data/standings/ --profile haekeo

# Test Bluesky post
python scripts/23_post_daily_summaries.py --type summary --force
```
