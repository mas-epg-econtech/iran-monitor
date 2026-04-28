#!/usr/bin/env python3
"""
One-off migration: add Regional CPI (Headline + Core, YoY) and Regional IPI
into iran_monitor.db for 10 Asian economies.

Series sourced from MAS economists' Indicators_28Apr2026.xlsx workbook:
  - 10 Headline CPI YoY series  (regional_cpi_headline_<iso2>)
  - 10 Core CPI YoY series       (regional_cpi_core_<iso2>)
  - 10 IPI / production indices  (regional_ipi_<iso2>)

Countries (ISO-2): cn, in, id, jp, my, ph, kr, tw, th, vn.

Why a one-off script vs running update_data.py:
  The full pipeline pulls every CEIC + Google Sheets + Comtrade + SingStat +
  Motorist series — it's slow and noisy. This script only touches the 30 new
  series, leaving everything else alone. The full pipeline will pick up these
  same series next time it runs (they're in SERIES_REGISTRY now).

Pattern (same as migrate_add_mas_core_mom.py):
  1. Login to CEIC, fetch each of the 30 series.
  2. Stage a scratch copy of iran_monitor.db at /tmp (FUSE bindfs mount on the
     Cowork folder doesn't fully support SQLite writes).
  3. INSERT OR REPLACE rows for each series.
  4. Verify: row counts + latest dates per series.
  5. Copy scratch back to live DB.

Run from the Iran Monitor root with the .env present:
    python3.11 scripts/migrate_add_regional_cpi_ipi.py

After it succeeds, rebuild dashboards:
    python3.11 scripts/build_iran_monitor.py
"""
from __future__ import annotations

import os
import shutil
import sqlite3
import sys
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
DB_SCRATCH = Path("/tmp") / "iran_monitor_regional_cpi_ipi.db"

# Make src.series_config importable
sys.path.insert(0, str(ROOT))
from src.series_config import SERIES_REGISTRY  # noqa: E402


# Which series this migration is responsible for. Keep these prefixes in sync
# with the keys we added to SERIES_REGISTRY.
TARGET_PREFIXES = ("regional_cpi_headline_", "regional_cpi_core_", "regional_ipi_")


def get_targets() -> list[tuple[str, dict]]:
    """Return [(series_id, registry_entry), ...] for series this migration owns."""
    out = []
    for sid, sdef in SERIES_REGISTRY.items():
        if sid.startswith(TARGET_PREFIXES):
            out.append((sid, sdef))
    return out


def fetch_series_from_ceic(source_key: str) -> list[tuple[str, float]]:
    """Pull a single CEIC series. Returns [(YYYY-MM-DD, value), ...] sorted."""
    from ceic_api_client.pyceic import Ceic

    result = Ceic.series_data(str(source_key))
    if not hasattr(result, "data") or not result.data:
        return []
    time_points = getattr(result.data[0], "time_points", []) or []
    rows: list[tuple[str, float]] = []
    for tp in time_points:
        try:
            d = str(tp.date)[:10]  # YYYY-MM-DD
            v = float(tp.value)
            rows.append((d, v))
        except (TypeError, ValueError, AttributeError):
            continue
    rows.sort()
    return rows


def main() -> None:
    if not DB_LIVE.exists():
        sys.exit(f"DB not found: {DB_LIVE}")

    targets = get_targets()
    if not targets:
        sys.exit("No target series found in SERIES_REGISTRY (check TARGET_PREFIXES).")

    user = os.environ.get("CEIC_USERNAME", "")
    pwd = os.environ.get("CEIC_PASSWORD", "")
    if not user or not pwd:
        sys.exit("CEIC_USERNAME / CEIC_PASSWORD not set (check Iran Monitor/.env).")

    # ── 1. Fetch all 30 series from CEIC up-front (so we abort cleanly if
    #       any fail before touching the DB). ────────────────────────────
    from ceic_api_client.pyceic import Ceic

    print(f"Logging in as {user}...")
    Ceic.login(user, pwd)
    print("Login OK\n")

    fetched: dict[str, tuple[dict, list[tuple[str, float]]]] = {}
    for sid, sdef in targets:
        source_key = sdef["source_key"]
        label = sdef.get("label", sid)
        print(f"  Fetching {sid:<32s} CEIC {source_key} — {label}")
        try:
            rows = fetch_series_from_ceic(source_key)
        except Exception as exc:
            print(f"    FAIL  {exc}")
            rows = []
        if not rows:
            print(f"    EMPTY (skipping in DB write)")
            continue
        print(f"    OK    {len(rows)} pts, latest {rows[-1][0]}")
        fetched[sid] = (sdef, rows)

    Ceic.logout()
    print(f"\nFetched {len(fetched)}/{len(targets)} series successfully.")

    if not fetched:
        sys.exit("No series fetched — aborting before any DB writes.")

    # ── 2. Stage scratch copy of DB ─────────────────────────────────────
    print(f"\nStaging DB at {DB_SCRATCH}")
    if DB_SCRATCH.exists():
        DB_SCRATCH.unlink()
    journal = DB_SCRATCH.with_suffix(DB_SCRATCH.suffix + "-journal")
    if journal.exists():
        journal.unlink()
    shutil.copy(DB_LIVE, DB_SCRATCH)

    conn = sqlite3.connect(DB_SCRATCH)

    # ── 3. Wipe any existing rows for these series, then insert fresh.
    #       (Idempotent — safe to re-run.) ──────────────────────────────
    placeholders = ",".join("?" for _ in fetched)
    n_deleted = conn.execute(
        f"DELETE FROM time_series WHERE series_id IN ({placeholders})",
        list(fetched.keys()),
    ).rowcount
    conn.commit()
    print(f"  Cleared {n_deleted} existing rows for the {len(fetched)} target series\n")

    # ── 4. Insert ────────────────────────────────────────────────────────
    total_inserted = 0
    for sid, (sdef, rows) in fetched.items():
        label = sdef.get("label", sid)
        unit = sdef.get("unit", "")
        frequency = sdef.get("frequency", "Monthly")
        conn.executemany(
            "INSERT OR REPLACE INTO time_series "
            "(date, value, series_id, series_name, source, unit, frequency, category) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, NULL)",
            [(d, v, sid, label, "ceic", unit, frequency) for d, v in rows],
        )
        total_inserted += len(rows)
    conn.commit()
    print(f"  Inserted {total_inserted} rows across {len(fetched)} series\n")

    # ── 5. Verify ────────────────────────────────────────────────────────
    print("=== Verification ===")
    for sid in sorted(fetched.keys()):
        r = conn.execute(
            "SELECT COUNT(*), MIN(date), MAX(date) FROM time_series WHERE series_id = ?",
            (sid,),
        ).fetchone()
        print(f"  {sid:<32s} | {r[0]:>4d} rows | {r[1]} → {r[2]}")

    conn.close()

    # ── 6. Copy back to live DB ─────────────────────────────────────────
    print(f"\nCopying {DB_SCRATCH.name} → {DB_LIVE}")
    shutil.copy(DB_SCRATCH, DB_LIVE)
    print("\nDone. Run `python3.11 scripts/build_iran_monitor.py` to re-render.")


if __name__ == "__main__":
    main()
