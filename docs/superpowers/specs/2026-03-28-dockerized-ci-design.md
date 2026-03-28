# Dockerized CI with Renovate — Design Spec

## Goal

Replace per-run dependency installation in GitHub Actions with a pre-built Docker image published to GHCR. Add Renovate to keep dependencies current.

## Docker Image

- **Base**: `python:3.9-slim`
- **Includes**: All Python packages from `requirements.txt` plus `pytz`, `pyarrow`, `fastparquet`, `lxml`, `beautifulsoup4`. Ruby 3.0, Bundler, Jekyll, and all gems from `Gemfile`. System font `fonts-roboto`.
- **Published to**: `ghcr.io/twallac10/mkebrewers-bot`
- **Tags**: `latest` (always updated) + short git SHA for rollback
- **Size**: ~1.2GB estimated (Python + Ruby + data libs)

## Image Build Workflow

**File**: `.github/workflows/build-image.yml`

**Triggers**:
- Push to `main` when any of these change: `Dockerfile`, `requirements.txt`, `Gemfile`, `Gemfile.lock`
- `workflow_dispatch` for manual rebuilds

**Steps**:
1. Checkout
2. Log in to GHCR (`docker/login-action`)
3. Build and push (`docker/build-push-action`) with tags `latest` + `sha-<short>`

**Permissions**: `packages: write`, `contents: read`

## Simplified Existing Workflows

All 6 workflows (`fetch.yml`, `fetch_historical.yml`, `post_summaries.yml`, `tweet_lineup.yml`, `post_news.yml`, `post_transactions.yml`) get:

- `container: ghcr.io/twallac10/mkebrewers-bot:latest` on each job
- **Removed steps**: Python setup, pip install, Ruby setup, bundle install, font install, mkdir for directories
- **Kept steps**: checkout, AWS credentials config, script execution, Jekyll build (in `fetch.yml`), GitHub Pages deploy, git commit/push

The `fetch.yml` workflow specifically keeps:
- Jekyll build (`bundle exec jekyll build`)
- GitHub Pages deploy (`peaceiris/actions-gh-pages@v4`)
- Git commit and push of data changes

## Renovate Configuration

**File**: `renovate.json`

**Manages**:
- `Dockerfile` base image tags (e.g., `python:3.9-slim` → `python:3.9.x-slim`)
- `requirements.txt` pip package versions (Renovate auto-detects)
- GitHub Actions versions in `.github/workflows/*.yml` (e.g., `actions/checkout@v4` → `@v5`)

**Does NOT manage**: `Gemfile` (Ruby deps baked into Docker image; updated via Dockerfile rebuild path)

**Policy**:
- Auto-merge: minor and patch updates
- PR required: major version bumps
- Schedule: weekly check window
- Group: Python dependency updates into a single PR

## File Changes Summary

| File | Action |
|------|--------|
| `Dockerfile` | Modify — add Ruby, Jekyll, Bundler, gems, fonts |
| `.github/workflows/build-image.yml` | Create — image build and push to GHCR |
| `.github/workflows/fetch.yml` | Modify — add container, remove setup steps |
| `.github/workflows/fetch_historical.yml` | Modify — add container, remove setup steps |
| `.github/workflows/post_summaries.yml` | Modify — add container, remove setup steps |
| `.github/workflows/tweet_lineup.yml` | Modify — add container, remove setup steps |
| `.github/workflows/post_news.yml` | Modify — add container, remove setup steps |
| `.github/workflows/post_transactions.yml` | Modify — add container, remove setup steps |
| `renovate.json` | Create — Renovate config |
