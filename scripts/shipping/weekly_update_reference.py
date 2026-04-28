#!/usr/bin/env python3
"""
Weekly Shipping Nowcast Update
==============================
Automated pipeline that:
  1. Downloads latest PortWatch data (ports + chokepoints)
  2. Runs the nowcast pipeline (STL + Ridge)
  3. Rebuilds the dashboard HTML
  4. Splices updated data into the GitHub Pages repo (preserving joint sigma code)
  5. Commits and pushes to GitHub

Designed to run as a weekly cron job on a VPS.

Usage:
  python weekly_update.py                    # full update
  python weekly_update.py --skip-download    # skip download, use existing data
  python weekly_update.py --dry-run          # do everything except git push

Cron example (every Wednesday 9pm SGT = 1pm UTC):
  0 13 * * 3 cd /path/to/Forecasting && python3 scripts/weekly_update.py >> logs/weekly_update.log 2>&1
"""

import os
import re
import subprocess
import sys
import time
from datetime import datetime

# ── Configuration ──────────────────────────────────────────────────────

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # Forecasting/
SCRIPTS_DIR = os.path.join(BASE_DIR, "scripts")
DATA_DIR = os.path.join(BASE_DIR, "data", "portwatch")
OUTPUT_DIR = os.path.join(BASE_DIR, "outputs", "nowcast")
REPO_DIR = os.path.join(BASE_DIR, "shipping-nowcast")  # git repo inside project dir
LOG_DIR = os.path.join(BASE_DIR, "logs")

# Git configuration
GIT_REMOTE = "origin"
GIT_BRANCH = "main"

# ── Helpers ────────────────────────────────────────────────────────────

def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)

def run_cmd(cmd, cwd=None, timeout=3600):
    """Run a shell command, return (success, stdout, stderr)."""
    log(f"  CMD: {cmd}")
    try:
        result = subprocess.run(
            cmd, shell=True, cwd=cwd, capture_output=True, text=True, timeout=timeout
        )
        if result.returncode != 0:
            log(f"  STDERR: {result.stderr.strip()}")
        return result.returncode == 0, result.stdout.strip(), result.stderr.strip()
    except subprocess.TimeoutExpired:
        log(f"  TIMEOUT after {timeout}s")
        return False, "", "timeout"

def get_max_date(csv_path, date_col_idx=0):
    """Get the max date string from a CSV file (first column by default)."""
    import csv
    max_date = ""
    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        next(reader)  # skip header
        for row in reader:
            if row and row[date_col_idx] > max_date:
                max_date = row[date_col_idx]
    return max_date.split(" ")[0]  # strip timezone if present


def extract_data_block(html, var_name):
    """Extract a JS variable assignment block like _kpiCountData = {...}"""
    start = html.find(f'{var_name} = {{')
    if start < 0:
        return None, None, None
    depth = 0
    i = html.index('{', start)
    for j in range(i, len(html)):
        if html[j] == '{':
            depth += 1
        elif html[j] == '}':
            depth -= 1
        if depth == 0:
            end = j + 1
            if end < len(html) and html[end] == ';':
                end += 1
            return start, end, html[start:end]
    return None, None, None


# ── Step 1: Download ──────────────────────────────────────────────────

def step_download():
    log("=" * 60)
    log("STEP 1: Downloading latest PortWatch data")
    log("=" * 60)

    # Record pre-download dates
    cp_path = os.path.join(DATA_DIR, "Daily_Chokepoints_Data.csv")
    ports_path = os.path.join(DATA_DIR, "Daily_Ports_Data.csv")

    old_cp_date = get_max_date(cp_path) if os.path.exists(cp_path) else "none"
    old_ports_date = get_max_date(ports_path) if os.path.exists(ports_path) else "none"
    log(f"  Current data: chokepoints={old_cp_date}, ports={old_ports_date}")

    # Run the download script
    ok, stdout, stderr = run_cmd(
        f"python3 {os.path.join(SCRIPTS_DIR, 'download_portwatch_data.py')}",
        cwd=BASE_DIR,
        timeout=3600  # ports download can take 30+ minutes
    )

    if not ok:
        log("  FAILED: Download failed")
        return False

    # Verify new dates
    new_cp_date = get_max_date(cp_path)
    new_ports_date = get_max_date(ports_path)
    log(f"  Updated data: chokepoints={new_cp_date}, ports={new_ports_date}")

    if new_cp_date <= old_cp_date and new_ports_date <= old_ports_date:
        log("  WARNING: No new data available (dates unchanged)")
        return False

    return True


# ── Step 2: Run Pipeline ─────────────────────────────────────────────

def step_pipeline():
    log("=" * 60)
    log("STEP 2: Running nowcast pipeline")
    log("=" * 60)

    ok, stdout, stderr = run_cmd(
        f"python3 {os.path.join(SCRIPTS_DIR, 'nowcast_pipeline.py')}",
        cwd=BASE_DIR,
        timeout=1800
    )

    if not ok:
        log("  FAILED: Pipeline failed")
        return False

    # Verify output exists
    results_path = os.path.join(OUTPUT_DIR, "nowcast_results_s13.json")
    if not os.path.exists(results_path):
        log(f"  FAILED: Expected output not found: {results_path}")
        return False

    log(f"  Pipeline output: {results_path}")
    return True


# ── Step 3: Build Dashboard ──────────────────────────────────────────

def step_build_dashboard():
    log("=" * 60)
    log("STEP 3: Building dashboard")
    log("=" * 60)

    ok, stdout, stderr = run_cmd(
        f"python3 {os.path.join(SCRIPTS_DIR, 'build_nowcast_dashboard.py')}",
        cwd=BASE_DIR,
        timeout=600
    )

    if not ok:
        log("  FAILED: Dashboard build failed")
        return False

    dashboard_path = os.path.join(OUTPUT_DIR, "hormuz_nowcast_dashboard.html")
    if not os.path.exists(dashboard_path):
        log(f"  FAILED: Dashboard not found: {dashboard_path}")
        return False

    size_mb = os.path.getsize(dashboard_path) / 1024 / 1024
    log(f"  Dashboard built: {dashboard_path} ({size_mb:.1f} MB)")
    return True


# ── Step 4: Update Repo Dashboard ────────────────────────────────────

def step_update_repo():
    log("=" * 60)
    log("STEP 4: Updating repo dashboard (preserving joint sigma)")
    log("=" * 60)

    new_dashboard = os.path.join(OUTPUT_DIR, "hormuz_nowcast_dashboard.html")
    repo_dashboard = os.path.join(REPO_DIR, "index.html")

    if not os.path.exists(repo_dashboard):
        log(f"  FAILED: Repo dashboard not found: {repo_dashboard}")
        return False

    with open(new_dashboard, "r") as f:
        new_html = f.read()
    with open(repo_dashboard, "r") as f:
        old_html = f.read()

    # Verify repo has joint sigma code
    if "computeJointSg" not in old_html:
        log("  WARNING: Repo dashboard missing joint sigma code, copying new dashboard as-is")
        with open(repo_dashboard, "w") as f:
            f.write(new_html)
        return True

    # Splice data blobs from new dashboard into repo dashboard
    for var in ['_kpiCountData', '_mapCountData', '_tableAggData']:
        s_new, e_new, block_new = extract_data_block(new_html, var)
        s_old, e_old, block_old = extract_data_block(old_html, var)
        if block_new and block_old:
            old_html = old_html[:s_old] + block_new + old_html[e_old:]
            log(f"  {var}: replaced {e_old - s_old} → {len(block_new)} chars")
        else:
            log(f"  WARNING: Could not extract {var}")

    # Update _postCrisisDates
    m_new = re.search(r'_postCrisisDates = \[([^\]]+)\]', new_html)
    m_old = re.search(r'_postCrisisDates = \[([^\]]+)\]', old_html)
    if m_new and m_old:
        new_dates_str = m_new.group(1)
        new_dates = [d.strip('"') for d in new_dates_str.split(',')]
        n_post = len(new_dates)

        old_html = old_html[:m_old.start()] + f'_postCrisisDates = [{new_dates_str}]' + old_html[m_old.end():]

        # Fix slider
        old_html = re.sub(
            r'weekSlider" min="0" max="\d+" step="1" value="\d+"',
            f'weekSlider" min="0" max="{n_post - 1}" step="1" value="{n_post - 1}"',
            old_html
        )

        # Fix selectedWeekIdx
        old_html = re.sub(
            r'window\._selectedWeekIdx = \d+;',
            f'window._selectedWeekIdx = {n_post - 1};',
            old_html
        )

        # Fix default week label
        old_html = re.sub(
            r'id="weekLabel"[^>]*>[^<]*</span>',
            f'id="weekLabel" style="font-weight:700;color:#fbbf24;min-width:5em;text-align:center;font-size:0.8rem;">{new_dates[-1]}</span>',
            old_html
        )

        log(f"  Post-crisis weeks: {n_post}, latest = {new_dates[-1]}")
    else:
        log("  WARNING: Could not update _postCrisisDates")

    with open(repo_dashboard, "w") as f:
        f.write(old_html)

    # Verify
    verify_joint = "computeJointSg" in old_html
    log(f"  Joint sigma preserved: {verify_joint}")

    return True


# ── Step 5: Git Commit & Push ────────────────────────────────────────

def step_git_push(dry_run=False):
    log("=" * 60)
    log("STEP 5: Committing and pushing to GitHub")
    log("=" * 60)

    if not os.path.exists(REPO_DIR):
        log(f"  FAILED: Repo directory not found: {REPO_DIR}")
        return False

    # Pull latest first
    ok, _, _ = run_cmd("git fetch origin", cwd=REPO_DIR)
    ok, _, _ = run_cmd("git rebase origin/main", cwd=REPO_DIR)

    # Check for changes
    ok, status, _ = run_cmd("git status --porcelain", cwd=REPO_DIR)
    if not status.strip():
        log("  No changes to commit")
        return True

    # Get latest data dates for commit message
    cp_path = os.path.join(DATA_DIR, "Daily_Chokepoints_Data.csv")
    ports_path = os.path.join(DATA_DIR, "Daily_Ports_Data.csv")
    cp_date = get_max_date(cp_path)
    ports_date = get_max_date(ports_path)

    # Count post-crisis weeks from the dashboard
    repo_dashboard = os.path.join(REPO_DIR, "index.html")
    with open(repo_dashboard) as f:
        html = f.read()
    m = re.search(r'_postCrisisDates = \[([^\]]+)\]', html)
    n_weeks = len(m.group(1).split(',')) if m else "?"
    dates = [d.strip('"') for d in m.group(1).split(',')] if m else []
    latest_week = dates[-1] if dates else "unknown"

    commit_msg = (
        f"Automated update: data through week of {latest_week} ({n_weeks} post-crisis weeks)\n\n"
        f"Ports data through {ports_date}, chokepoints through {cp_date}.\n"
        f"Pipeline re-run with updated PortWatch data.\n\n"
        f"Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
    )

    # Stage and commit
    run_cmd("git add index.html", cwd=REPO_DIR)
    ok, _, _ = run_cmd(f'git commit -m "{commit_msg}"', cwd=REPO_DIR)

    if not ok:
        log("  FAILED: git commit failed")
        return False

    if dry_run:
        log("  DRY RUN: skipping push")
        return True

    ok, _, stderr = run_cmd(f"git push {GIT_REMOTE} {GIT_BRANCH}", cwd=REPO_DIR)
    if not ok:
        log(f"  FAILED: git push failed: {stderr}")
        return False

    log("  Pushed successfully")
    return True


# ── Main ──────────────────────────────────────────────────────────────

def main():
    args = set(sys.argv[1:])
    skip_download = "--skip-download" in args
    dry_run = "--dry-run" in args

    os.makedirs(LOG_DIR, exist_ok=True)

    log("=" * 60)
    log("SHIPPING NOWCAST — WEEKLY UPDATE")
    log(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log(f"Options: skip_download={skip_download}, dry_run={dry_run}")
    log("=" * 60)

    start = time.time()
    steps = []

    # Step 1: Download
    if not skip_download:
        ok = step_download()
        steps.append(("Download", ok))
        if not ok:
            log("\nDownload failed or no new data. Aborting.")
            sys.exit(1)
    else:
        log("Skipping download (--skip-download)")

    # Step 2: Pipeline
    ok = step_pipeline()
    steps.append(("Pipeline", ok))
    if not ok:
        log("\nPipeline failed. Aborting.")
        sys.exit(1)

    # Step 3: Build dashboard
    ok = step_build_dashboard()
    steps.append(("Dashboard", ok))
    if not ok:
        log("\nDashboard build failed. Aborting.")
        sys.exit(1)

    # Step 4: Update repo
    ok = step_update_repo()
    steps.append(("Repo update", ok))
    if not ok:
        log("\nRepo update failed. Aborting.")
        sys.exit(1)

    # Step 5: Push
    ok = step_git_push(dry_run=dry_run)
    steps.append(("Git push", ok))

    # Summary
    elapsed = time.time() - start
    log("\n" + "=" * 60)
    log("SUMMARY")
    log("=" * 60)
    for name, ok in steps:
        status = "OK" if ok else "FAILED"
        log(f"  {name}: {status}")
    log(f"  Total time: {elapsed:.0f}s ({elapsed/60:.1f}m)")

    if all(ok for _, ok in steps):
        log("\nAll steps completed successfully.")
    else:
        log("\nSome steps failed. Check log above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
