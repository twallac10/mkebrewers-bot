#!/usr/bin/env python
# coding: utf-8

"""
Updates hardcoded year references for a new season.

Usage:
    python scripts/update_season_year.py --old-year 2025 --new-year 2026 [--dry-run]

This script updates:
- Postseason section headers
- Postseason data file references
- Year-over-year comparison charts
- Pitch data download links
- Jekyll data fallbacks
"""

import argparse
import re
import sys
from pathlib import Path
from typing import List, Tuple

# ANSI color codes for terminal output
GREEN = '\033[92m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RED = '\033[91m'
RESET = '\033[0m'
BOLD = '\033[1m'

def update_file(file_path: Path, replacements: List[Tuple[str, str]], dry_run: bool = False) -> bool:
    """
    Update a file with the given replacements.

    Args:
        file_path: Path to the file to update
        replacements: List of (old_text, new_text) tuples
        dry_run: If True, don't actually modify the file

    Returns:
        True if changes were made (or would be made in dry-run), False otherwise
    """
    if not file_path.exists():
        print(f"{RED}✗{RESET} File not found: {file_path}")
        return False

    try:
        content = file_path.read_text()
        original_content = content
        changes_made = []

        for old_text, new_text in replacements:
            if old_text in content:
                count = content.count(old_text)
                content = content.replace(old_text, new_text)
                changes_made.append((old_text, new_text, count))

        if changes_made:
            if not dry_run:
                file_path.write_text(content)
                print(f"{GREEN}✓{RESET} Updated {BOLD}{file_path.relative_to(Path.cwd())}{RESET}")
            else:
                print(f"{YELLOW}[DRY RUN]{RESET} Would update {BOLD}{file_path.relative_to(Path.cwd())}{RESET}")

            for old, new, count in changes_made:
                preview_old = old[:60] + "..." if len(old) > 60 else old
                preview_new = new[:60] + "..." if len(new) > 60 else new
                print(f"  {count}× '{preview_old}' → '{preview_new}'")

            return True
        else:
            print(f"{BLUE}○{RESET} No changes needed in {file_path.relative_to(Path.cwd())}")
            return False

    except Exception as e:
        print(f"{RED}✗{RESET} Error updating {file_path}: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(
        description="Update hardcoded year references for a new baseball season",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Preview changes for 2026 season
  python scripts/update_season_year.py --old-year 2025 --new-year 2026 --dry-run

  # Apply changes for 2026 season
  python scripts/update_season_year.py --old-year 2025 --new-year 2026

  # Future: Update for 2027 season
  python scripts/update_season_year.py --old-year 2026 --new-year 2027
        """
    )
    parser.add_argument('--old-year', type=int, required=True, help='Previous season year (e.g., 2025)')
    parser.add_argument('--new-year', type=int, required=True, help='New season year (e.g., 2026)')
    parser.add_argument('--dry-run', action='store_true', help='Preview changes without modifying files')

    args = parser.parse_args()

    old_year = str(args.old_year)
    new_year = str(args.new_year)
    prev_year = str(args.old_year - 1)

    print(f"\n{BOLD}Season Year Update: {old_year} → {new_year}{RESET}")
    print(f"Mode: {YELLOW}DRY RUN{RESET}" if args.dry_run else f"Mode: {GREEN}LIVE{RESET}")
    print("=" * 60)

    repo_root = Path.cwd()
    files_updated = 0

    # 1. Comment out postseason section in index.markdown
    print(f"\n{BOLD}1. Comment Out Postseason Section{RESET}")
    print(f"{YELLOW}⚠{RESET}  Postseason section will be commented out until {new_year} playoffs begin")
    index_file = repo_root / "index.markdown"

    # Comment out the entire postseason section
    postseason_section = f'''<div class="postseason-stats-section">
  <h2 class="stat-group postseason-header">Postseason {old_year}</h2>

  <h3 class="visual-subhead">Playoff journey</h3>
  <div class="playoff-journey" id="playoff-journey">
    <!-- Playoff journey will be populated by JavaScript -->
  </div>

  <h3 class="visual-subhead">Team hitting</h3>
  <div class="postseason-grid" id="postseason-grid">
    <!-- Postseason stats will be populated by JavaScript -->
  </div>
  <p class="note">Note: Top 12 players in order of plate appearances.</p>
</div>'''

    commented_section = f'''<!-- Postseason section commented out - uncomment when {new_year} playoffs begin
<div class="postseason-stats-section">
  <h2 class="stat-group postseason-header">Postseason {new_year}</h2>

  <h3 class="visual-subhead">Playoff journey</h3>
  <div class="playoff-journey" id="playoff-journey">
    <!-- Playoff journey will be populated by JavaScript -->
  </div>

  <h3 class="visual-subhead">Team hitting</h3>
  <div class="postseason-grid" id="postseason-grid">
    <!-- Postseason stats will be populated by JavaScript -->
  </div>
  <p class="note">Note: Top 12 players in order of plate appearances.</p>
</div>
-->'''

    if update_file(index_file, [(postseason_section, commented_section)], args.dry_run):
        files_updated += 1
        print(f"  {YELLOW}→{RESET} Uncomment this section in index.markdown when playoffs start")

    # 2. Update postseason data file references in dashboard.js
    print(f"\n{BOLD}2. Postseason Data Files{RESET}")
    dashboard_file = repo_root / "assets/js/dashboard.js"
    if update_file(dashboard_file, [
        (f'/assets/data/postseason/redsox_postseason_stats_{old_year}.json',
         f'/assets/data/postseason/redsox_postseason_stats_{new_year}.json'),
        (f'redsox/data/postseason/redsox_postseason_stats_{old_year}.json',
         f'redsox/data/postseason/redsox_postseason_stats_{new_year}.json'),
        (f'/assets/data/postseason/redsox_postseason_series_{old_year}.json',
         f'/assets/data/postseason/redsox_postseason_series_{new_year}.json'),
        (f'redsox/data/postseason/redsox_postseason_series_{old_year}.json',
         f'redsox/data/postseason/redsox_postseason_series_{new_year}.json'),
    ], args.dry_run):
        files_updated += 1

    # 3. Update year-over-year comparison labels and filters
    print(f"\n{BOLD}3. Year-over-Year Comparison Charts{RESET}")
    print(f"{YELLOW}⚠{RESET}  Note: This updates data filters and labels")
    print(f"   Old comparison: {prev_year} vs {old_year}")
    print(f"   New comparison: {old_year} vs {new_year}")

    # Update all references to the current season in comparisons
    yoy_replacements = [
        # Update season filters
        (f'const data{old_year} = data.filter(d => d.season === {old_year});',
         f'const data{new_year} = data.filter(d => d.season === {new_year});'),
        (f'const data{old_year}_hr = hrData.filter(d => d.season === {old_year});',
         f'const data{new_year}_hr = hrData.filter(d => d.season === {new_year});'),

        # Update variable names
        (f'data{old_year}', f'data{new_year}'),
        (f'last{old_year}', f'last{new_year}'),
        (f'line{old_year}', f'line{new_year}'),
        (f'label{old_year}', f'label{new_year}'),
        (f'xPosText{old_year}', f'xPosText{new_year}'),
        (f'yPosLabel{old_year}', f'yPosLabel{new_year}'),
        (f'yPosStat{old_year}', f'yPosStat{new_year}'),
        (f'lastGameEntry{old_year}', f'lastGameEntry{new_year}'),
        (f'lastGameNumber{old_year}', f'lastGameNumber{new_year}'),

        # Update text labels
        (f".text('{old_year}')", f".text('{new_year}')"),
        (f'// {old_year}', f'// {new_year}'),
        (f'with {old_year}', f'with {new_year}'),
    ]

    if update_file(dashboard_file, yoy_replacements, args.dry_run):
        files_updated += 1

    # 4. Update Jekyll data fallback
    print(f"\n{BOLD}4. Jekyll Data Fallback{RESET}")
    if update_file(index_file, [
        (f'site.data.standings.all_teams_standings_metrics_{old_year}',
         f'site.data.standings.all_teams_standings_metrics_{new_year}'),
        (f'Fallback to {old_year} data',
         f'Fallback to {new_year} data'),
    ], args.dry_run):
        files_updated += 1

    # 5. Update pitch data download links
    print(f"\n{BOLD}5. Pitch Data Download Links{RESET}")
    if update_file(index_file, [
        (f'dodgers_pitches_{old_year}.json', f'redsox_pitches_{new_year}.json'),
        (f'redsox_pitches_{old_year}.json', f'redsox_pitches_{new_year}.json'),
    ], args.dry_run):
        files_updated += 1

    # Summary
    print("\n" + "=" * 60)
    if args.dry_run:
        print(f"{YELLOW}{BOLD}DRY RUN COMPLETE{RESET}")
        print(f"{files_updated} file(s) would be updated")
        print(f"\nTo apply changes, run without --dry-run:")
        print(f"  python scripts/update_season_year.py --old-year {old_year} --new-year {new_year}")
    else:
        print(f"{GREEN}{BOLD}UPDATE COMPLETE{RESET}")
        print(f"{files_updated} file(s) updated")
        print(f"\n{BOLD}Next steps:{RESET}")
        print(f"1. Review changes: git diff")
        print(f"2. Test the site locally: bundle exec jekyll serve")
        print(f"3. Commit changes: git add -A && git commit -m 'Update to {new_year} season'")
        print(f"4. Push to GitHub: git push")

    print("\n" + "=" * 60)
    return 0

if __name__ == "__main__":
    sys.exit(main())
