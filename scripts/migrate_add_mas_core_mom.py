#!/usr/bin/env python3
"""
One-off migration: add MAS Core Inflation MoM to iran_monitor.db.

What this does:
  1. Fetches MAS Core Inflation Index (level, CEIC id 541733607) into the DB.
  2. Computes month-on-month % change from the level and inserts as a derived
     series (series_id='mas_core_inflation_mom', source='derived').
  3. Both ops use the /tmp scratch pattern (FUSE bindfs mount on the user's
     Cowork folder doesn't fully support SQLite writes; see migrate_to_iran_monitor_db.py).

Run from the Iran Monitor root with the .env present:
  python3.11 scripts/migrate_add_mas_core_mom.py

After it succeeds, rebuild dashboards:
  python3.11 scripts/build_iran_monitor.py
"""
from __future__ import annotations

import os
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path


# ── .env auto-loader ─────────────────────────────────────────────────────
def _load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, _, v = s.partition("=")
        os.environ.setdefault(k.strip(), v.strip().strip("'\""))


ROOT = Path(__file__).resolve().parent.parent
_load_env(ROOT / ".env")
_load_env(Path("/Users/kevinlim/Documents/MAS/Projects/ESD/Middle East Dashboard/.env"))

DB_LIVE = ROOT / "data" / "iran_monitor.db"
DB_SCRATCH = Path("/tmp") / "iran_monitor_mas_core_mom.db"

LEVEL_SERIES_ID = "ceic_mas_core_inflation_index"
LEVEL_CEIC_ID = "541733607"
LEVEL_LABEL = "MAS Core Inflation Index"
LEVEL_UNIT = "2024=100"

# Make src.derived_series importable
sys.path.insert(0, str(ROOT))


def fetch_level_series_from_ceic() -> list[tuple[str, float]]:
    """Pull the MAS Core Inflation Index (level) from CEIC. Returns [(date, value), ...]."""
    try:
        from ceic_api_client.pyceic import Ceic
    except ImportError:
        sys.exit("ceic_api_client not installed for this Python interpreter.")

    user = os.environ.get("CEIC_USERNAME", "")
    pwd = os.environ.get("CEIC_PASSWORD", "")
    if not user or not pwd:
        sys.exit("CEIC_USERNAME / CEIC_PASSWORD not set (check Iran Monitor/.env).")

    print(f"Logging in as {user}...")
    Ceic.login(user, pwd)
    print("Login OK\n")

    print(f"Fetching CEIC series {LEVEL_CEIC_ID} (MAS Core Inflation Index)...")
    result = Ceic.series_data(LEVEL_CEIC_ID)
    if not hasattr(result, "data") or not result.data:
        sys.exit(f"  EMPTY response for CEIC id {LEVEL_CEIC_ID}")

    time_points = getattr(result.data[0], "time_points", []) or []
    if not time_points:
        sys.exit(f"  No time_points in CEIC response")

    rows: list[tuple[str, float]] = []
    for tp in time_points:
        try:
            d = str(tp.date)[:10]  # YYYY-MM-DD
            v = float(tp.value)
            rows.append((d, v))
        except (TypeError, ValueError, AttributeError):
            continue
    rows.sort()
    print(f"  Got {len(rows)} data points, latest {rows[-1][0] if rows else '?'}")
    Ceic.logout()
    return rows


def main() -> None:
    if not DB_LIVE.exists():
        sys.exit(f"DB not found: {DB_LIVE}")

    # 1. Fetch the level series from CEIC
    level_rows = fetch_level_series_from_ceic()
    if not level_rows:
        sys.exit("No level data fetched — aborting before any DB writes")

    # 2. Stage scratch copy of DB
    print(f"\nStaging DB at {DB_SCRATCH}")
    if DB_SCRATCH.exists():
        DB_SCRATCH.unlink()
    journal = DB_SCRATCH.with_suffix(DB_SCRATCH.suffix + "-journal")
    if journal.exists():
        journal.unlink()
    shutil.copy(DB_LIVE, DB_SCRATCH)

    conn = sqlite3.connect(DB_SCRATCH)

    # 3. Wipe any existing rows for the level + derived MoM (for clean re-runs)
    n_deleted = conn.execute(
        "DELETE FROM time_series WHERE series_id IN (?, ?)",
        (LEVEL_SERIES_ID, "mas_core_inflation_mom"),
    ).rowcount
    conn.commit()
    print(f"  Cleared {n_deleted} existing rows for {LEVEL_SERIES_ID} / mas_core_inflation_mom")

    # 4. Insert level series
    conn.executemany(
        "INSERT OR REPLACE INTO time_series "
        "(date, value, series_id, series_name, source, unit, frequency, category) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, NULL)",
        [(d, v, LEVEL_SERIES_ID, LEVEL_LABEL, "ceic", LEVEL_UNIT, "Monthly") for d, v in level_rows],
    )
    conn.commit()
    print(f"  Inserted {len(level_rows)} level rows")

    # 5. Compute MoM via the reusable derivation function
    from src.derived_series import compute_mas_core_mom
    n_mom = compute_mas_core_mom(conn)
    print(f"  Computed + inserted {n_mom} MoM rows")

    # 6. Verify
    print("\n=== Verification ===")
    for sid in (LEVEL_SERIES_ID, "mas_core_inflation_mom"):
        r = conn.execute(
            "SELECT MAX(date), COUNT(*), MIN(date) FROM time_series WHERE series_id = ?",
            (sid,),
        ).fetchone()
        print(f"  {sid:<35} | {r[1]} rows | {r[2]} → {r[0]}")
    # Show a few recent MoM values for sanity
    print("\n  Recent MoM values:")
    for date, val in conn.execute(
        "SELECT date, value FROM time_series WHERE series_id = 'mas_core_inflation_mom' "
        "ORDER BY date DESC LIMIT 6"
    ):
        print(f"    {date}: {val:+.3f}%")

    conn.close()

    # 7. Copy back to live DB
    print(f"\nCopying {DB_SCRATCH.name} → {DB_LIVE}")
    shutil.copy(DB_SCRATCH, DB_LIVE)
    print("\nDone. Run `python3.11 scripts/build_iran_monitor.py` to re-render.")


if __name__ == "__main__":
    main()
