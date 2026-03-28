# Red Sox Data Bot - Complete Setup Guide

This guide will walk you through setting up the Red Sox Data Bot from scratch. Follow these steps in order for a smooth setup experience.

## Prerequisites

Before you begin, ensure you have:

- [ ] GitHub account
- [ ] AWS account (for S3 data storage)
- [ ] Basic familiarity with command line
- [ ] Python 3.9+ installed locally (for testing)
- [ ] Git installed locally

## Part 1: Fork and Clone Repository

### Step 1: Fork the Repository

1. Visit the repository on GitHub
2. Click the **Fork** button in the top right
3. Select your account as the destination
4. Wait for GitHub to create your fork

### Step 2: Clone Your Fork

```bash
git clone https://github.com/YOUR-USERNAME/redsox-bot.git
cd redsox-bot
```

### Step 3: Install Dependencies

**For Python scripts:**
```bash
pip install -r requirements.txt
```

**For Jekyll site (optional, for local testing):**
```bash
gem install bundler
bundle install
```

## Part 2: AWS S3 Setup

### Step 4: Create S3 Bucket

1. Log into [AWS Console](https://console.aws.amazon.com/)
2. Navigate to **S3** service
3. Click **Create bucket**
4. Enter bucket name: `your-domain.com` (or any unique name)
5. Select region: `us-west-1` (or your preferred region)
6. **Uncheck** "Block all public access"
7. Acknowledge the public access warning
8. Click **Create bucket**

### Step 5: Configure Bucket Policy

1. Click on your newly created bucket
2. Go to **Permissions** tab
3. Scroll to **Bucket Policy** section
4. Click **Edit**
5. Paste this policy (replace `YOUR-BUCKET-NAME`):

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "PublicReadGetObject",
            "Effect": "Allow",
            "Principal": "*",
            "Action": "s3:GetObject",
            "Resource": "arn:aws:s3:::YOUR-BUCKET-NAME/redsox/*"
        }
    ]
}
```

6. Click **Save changes**

### Step 6: Create IAM User for GitHub Actions

1. Navigate to **IAM** service
2. Click **Users** in the left sidebar
3. Click **Add users**
4. User name: `github-actions-redsox-bot`
5. Select **Access key - Programmatic access**
6. Click **Next: Permissions**
7. Select **Attach existing policies directly**
8. Search for and check **AmazonS3FullAccess**
9. Click **Next: Tags** (skip this step)
10. Click **Next: Review**
11. Click **Create user**
12. **IMPORTANT:** Copy the **Access Key ID** and **Secret Access Key**
    - Save these somewhere secure — you'll need them in Step 8
    - You won't be able to see the secret key again

## Part 3: GitHub Configuration

### Step 7: Update Repository Settings

1. Go to your forked repository on GitHub
2. Click **Settings** → **Pages**
3. Under **Source**, select **Deploy from a branch**
4. Select branch: **gh-pages** (or **main** if gh-pages doesn't exist yet)
5. Click **Save**

### Step 8: Add GitHub Secrets

1. In your repository, go to **Settings** → **Secrets and variables** → **Actions**
2. Click **New repository secret**
3. Add the following secrets one by one:

| Name | Value |
|------|-------|
| `AWS_ACCESS_KEY_ID` | Your AWS Access Key from Step 6 |
| `AWS_SECRET_ACCESS_KEY` | Your AWS Secret Key from Step 6 |

**Note:** Twitter secrets are not needed unless you plan to re-enable Twitter functionality.

### Step 9: Update Configuration Files

Edit `scripts/config.py` to match your setup:

```python
# S3 Configuration
S3_BUCKET = "your-bucket-name"  # Change to your bucket name
S3_PREFIX = "redsox"
AWS_REGION = "us-west-1"  # Change if you used a different region
```

**Commit your changes:**
```bash
git add scripts/config.py
git commit -m "Update S3 configuration"
git push origin main
```

## Part 4: Initial Data Population

### Step 10: Trigger Initial Data Fetch

1. Go to **Actions** tab in your GitHub repository
2. Select **Fetch and process data** workflow (fetch.yml)
3. Click **Run workflow** dropdown
4. Select branch: **main**
5. Click **Run workflow**
6. Wait for the workflow to complete (typically 10-20 minutes)
7. Monitor progress by clicking on the running workflow

**What this does:**
- Fetches current season standings from Baseball Reference
- Fetches batting and pitching statistics
- Processes and combines with historical data
- Uploads everything to your S3 bucket
- Generates JSON, CSV, and Parquet files

### Step 11: Verify Data Upload

Check that data was uploaded to S3:

1. Go to **AWS Console** → **S3**
2. Click on your bucket
3. Navigate to `redsox/data/`
4. You should see folders: `standings/`, `batting/`, `pitching/`, etc.
5. Test public access with curl:

```bash
curl -I https://YOUR-BUCKET-NAME.s3.us-west-1.amazonaws.com/redsox/data/standings/season_summary_latest.json
# Should return HTTP 200 OK
```

**If you get 403 Forbidden:**
- Double-check your bucket policy from Step 5
- Ensure the policy specifies the correct bucket name and path

## Part 5: Build and Deploy Website

### Step 12: Test Site Locally (Optional)

Before deploying, test the site on your local machine:

```bash
bundle exec jekyll serve
```

Visit `http://localhost:4000` in your browser. You should see:
- Red Sox branding and colors
- Charts (if data files exist)
- Roster and transactions pages

**Troubleshooting local builds:**
- If charts are empty, that's normal — they load data from S3, not local files
- Press `Ctrl+C` to stop the local server

### Step 13: Deploy to GitHub Pages

1. Go to **Actions** tab
2. Select **Build site** workflow (build_site.yml)
3. Click **Run workflow**
4. Wait for completion (typically 2-3 minutes)
5. Once complete, your site will be live!

**Access your site:**
- Default URL: `https://YOUR-USERNAME.github.io/redsox-bot/`
- Custom domain (if configured): `https://redsoxdata.bot/`

### Step 14: Verify Deployment

Visit your site and check:
- [ ] Site loads without errors
- [ ] Red Sox colors are visible (red #BD3039, navy #0C2340)
- [ ] No Dodgers branding remains
- [ ] Dashboard charts display data
- [ ] Roster page loads
- [ ] Transactions page loads
- [ ] About page shows correct content

## Part 6: Custom Domain (Optional)

### Step 15: Configure DNS

If you have a custom domain (e.g., `redsoxdata.bot`):

1. Log into your domain registrar (Namecheap, Google Domains, etc.)
2. Go to DNS settings for your domain
3. Add these **A records**:

```
Type    Host    Value               TTL
A       @       185.199.108.153     Automatic
A       @       185.199.109.153     Automatic
A       @       185.199.110.153     Automatic
A       @       185.199.111.153     Automatic
```

4. Add a **CNAME record** for www subdomain:

```
Type    Host    Value                           TTL
CNAME   www     YOUR-USERNAME.github.io         Automatic
```

5. Save DNS changes

### Step 16: Configure Custom Domain in GitHub

1. Go to **Settings** → **Pages**
2. Under **Custom domain**, enter your domain: `redsoxdata.bot`
3. Click **Save**
4. Wait for DNS check to complete (can take 5-60 minutes)
5. Once verified, check **Enforce HTTPS**

**Verify DNS propagation:**
```bash
dig redsoxdata.bot +short
# Should show GitHub Pages IPs
```

**Wait for HTTPS certificate:**
- GitHub automatically provisions SSL via Let's Encrypt
- This can take 10-30 minutes after DNS propagates
- You'll see a checkmark when it's ready

## Part 7: Automation Setup

### Step 17: Enable Automated Workflows

Your repository includes these automated workflows:

| Workflow | File | Default Schedule | Status |
|----------|------|------------------|--------|
| Fetch data | `.github/workflows/fetch.yml` | Every 3 hours | ✅ Enabled |
| Build site | `.github/workflows/build_site.yml` | Daily at 12:00 UTC | ✅ Enabled |
| Post summaries | `.github/workflows/post_summaries.yml` | Various times | ⏸️ Disabled |
| Tweet lineup | `.github/workflows/tweet_lineup.yml` | Hourly | ⏸️ Disabled |
| Post news | `.github/workflows/post_news.yml` | Daily at 15:00 UTC | ⏸️ Disabled |
| Post transactions | `.github/workflows/post_transactions.yml` | Every 6 hours | ⏸️ Disabled |

**Twitter workflows are disabled by default.** To enable them, you'll need to:
1. Create a Twitter Developer account
2. Create an app and get API credentials
3. Add Twitter secrets to GitHub (see README.md Security section)
4. Uncomment the schedule triggers in the workflow files

### Step 18: Monitor First Automated Run

1. Wait for the next scheduled `fetch.yml` run (every 3 hours)
2. Go to **Actions** tab to monitor it
3. Verify it completes successfully
4. Check S3 to see updated data files
5. Visit your site to see fresh data

**If the workflow fails:**
- Click on the failed run to see error logs
- Common issues: rate limiting from Baseball Reference (wait and retry)
- Re-run the workflow manually

## Part 8: Ongoing Maintenance

### Daily Monitoring Checklist

Check these once daily during baseball season:

- [ ] Visit **Actions** tab — verify recent workflows succeeded
- [ ] Check your live site — ensure data is current
- [ ] Monitor AWS billing — should be $2-5/month

### Weekly Tasks

- [ ] Review any failed workflow runs and retry
- [ ] Verify all data endpoints are accessible
- [ ] Check GitHub Actions usage (should stay under free tier)

### Monthly Tasks

- [ ] Review and clear old workflow runs (optional)
- [ ] Check AWS S3 storage size and costs
- [ ] Update Python dependencies if needed:
  ```bash
  pip install --upgrade -r requirements.txt
  ```

### Off-Season Maintenance

During the off-season (November-February):

1. Reduce workflow frequency to save GitHub Actions minutes:
   - Edit `.github/workflows/fetch.yml`
   - Change schedule from every 3 hours to daily or weekly
2. Keep site running for historical data access
3. Re-enable frequent updates before spring training starts

## Troubleshooting Setup Issues

### "Workflow not running automatically"

**Check:**
- Go to **Actions** tab → Click on the workflow
- Ensure the workflow is enabled (there's an enable/disable toggle)
- Verify the schedule syntax in the YAML file

### "S3 upload failed: NoCredentialsError"

**Fix:**
- Verify `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` secrets are set
- Check for typos in secret names (they're case-sensitive)
- Ensure IAM user has S3 permissions

### "Site shows 404 error"

**Fix:**
- Go to **Settings** → **Pages**
- Verify source branch is set correctly
- Check that `gh-pages` branch exists and has content
- Try manually running the `build_site.yml` workflow

### "Charts are empty on the site"

**Check:**
1. Data files exist in S3: `https://YOUR-BUCKET-NAME.s3.amazonaws.com/redsox/data/standings/redsox_standings_1901_present_optimized.json`
2. Bucket policy allows public read access
3. Browser console for JavaScript errors (F12 → Console)
4. File path in `assets/js/dashboard.js` matches S3 file names

### "Still seeing Dodgers branding"

**This means the conversion wasn't complete. Check:**
- `_sass/custom.scss` — should use Red Sox colors (#BD3039, #0C2340)
- `about.md` — should reference Red Sox, not Dodgers
- Clear browser cache completely
- Hard refresh: Cmd+Shift+R (Mac) or Ctrl+F5 (Windows)

## Success Checklist

You're fully set up when you can check all these boxes:

- [ ] Repository forked and cloned
- [ ] S3 bucket created with public read policy
- [ ] IAM user created with access keys
- [ ] GitHub secrets configured (AWS keys)
- [ ] Initial data fetch completed successfully
- [ ] Data visible in S3 bucket
- [ ] Site deployed to GitHub Pages
- [ ] Site accessible at your URL
- [ ] Dashboard charts displaying data
- [ ] Red Sox branding visible (no Dodgers references)
- [ ] Automated workflows running on schedule
- [ ] AWS billing set up and monitored

## Next Steps

Once setup is complete:

1. **Customize the site**: Edit `about.md` with your personal information
2. **Add features**: Consider adding new stats or visualizations
3. **Monitor regularly**: Check the Actions tab daily during season
4. **Join the community**: Share your bot on social media
5. **Contribute back**: If you add cool features, consider submitting a pull request!

## Getting Help

If you run into issues:

1. Check the **Troubleshooting** section in README.md
2. Review workflow logs in the **Actions** tab
3. Search existing GitHub Issues
4. Open a new issue with:
   - What you were trying to do
   - What happened instead
   - Relevant error messages or screenshots
   - Your setup (OS, Python version, etc.)

## Additional Resources

- [GitHub Pages Documentation](https://docs.github.com/en/pages)
- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [AWS S3 Documentation](https://docs.aws.amazon.com/s3/)
- [Jekyll Documentation](https://jekyllrb.com/docs/)
- [Baseball Reference](https://www.baseball-reference.com/)
- [Baseball Savant](https://baseballsavant.mlb.com/)

---

**Congratulations!** 🎉 Your Red Sox Data Bot is now live and automatically updating.
