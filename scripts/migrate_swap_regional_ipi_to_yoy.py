#!/usr/bin/env python3
"""
One-off migration: swap the 10 Regional IPI series in iran_monitor.db from
their previous level-index sources to the YoY % series picked from the
2026-04-28 freshness audit.

What changes:
  - Old: each country's official IPI level (different base years, China stale
    since Nov 2022, Indonesia ends Dec 2025).
  - New: each country's % YoY series (single comparable scale, all but
    Indonesia fresh through 2026-Q1).

The 10 series_ids stay the same (regional_ipi_<iso2>); only the underlying
CEIC source_key + unit + label change. SERIES_REGISTRY has already been
updated with the new source_keys; this script reads from there.

Pattern (same as migrate_add_regional_cpi_ipi.py):
  1. Login to CEIC, fetch each of the 10 NEW series.
  2. Stage scratch DB at /tmp (FUSE mount doesn't fully support SQLite writes).
  3. DELETE all existing rows for the 10 series_ids (clears stale level data).
  4. INSERT the new YoY rows.
  5. Verify, copy back.

Run from the Iran Monitor root with .env present:
  python3.11 scripts/migrate_swap_regional_ipi_to_yoy.py

Then rebuild:
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
DB_SCRATCH = Path("/tmp") / "iran_monitor_swap_regional_ipi.db"

sys.path.insert(0, str(ROOT))
from src.series_config import SERIES_REGISTRY  # noqa: E402


# This migration ONLY touches these series_ids — all others left alone.
TARGET_PREFIX = "regional_ipi_"


def get_targets() -> list[tuple[str, dict]]:
    """Return [(series_id, registry_entry)] for the 10 regional IPI series."""
    return [
        (sid, sdef) for sid, sdef in SERIES_REGISTRY.items()
        if sid.startswith(TARGET_PREFIX)
    ]


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
            d = str(tp.date)[:10]
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
    if len(targets) != 10:
        sys.exit(f"Expected 10 regional_ipi_* entries in SERIES_REGISTRY; found {len(targets)}.")

    user = os.environ.get("CEIC_USERNAME", "")
    pwd = os.environ.get("CEIC_PASSWORD", "")
    if not user or not pwd:
        sys.exit("CEIC_USERNAME / CEIC_PASSWORD not set (check Iran Monitor/.env).")

    # Sanity check: the new source_keys should NOT be the old level-index ids.
    OLD_LEVEL_IDS = {"371937157", "386587797", "322957602", "508465317",
                     "402561157", "458913927", "505286737", "508241517",
                     "522375327", "389657597"}
    for sid, sdef in targets:
        if str(sdef["source_key"]) in OLD_LEVEL_IDS:
            sys.exit(
                f"{sid} still points at an OLD level-index CEIC id "
                f"({sdef['source_key']}). Update src/series_config.py first."
            )

    # ── 1. Fetch all 10 series upfront ──────────────────────────────────
    from ceic_api_client.pyceic import Ceic

    print(f"Logging in as {user}...")
    Ceic.login(user, pwd)
    print("Login OK\n")

    fetched: dict[str, tuple[dict, list[tuple[str, float]]]] = {}
    for sid, sdef in targets:
        source_key = sdef["source_key"]
        label = sdef.get("label", sid)
        print(f"  Fetching {sid:<24s} CEIC {source_key} — {label}")
        try:
            rows = fetch_series_from_ceic(source_key)
        except Exception as exc:
            print(f"    FAIL  {exc}")
            rows = []
        if not rows:
            print(f"    EMPTY (skipping)")
            continue
        print(f"    OK    {len(rows)} pts, latest {rows[-1][0]}")
        fetched[sid] = (sdef, rows)

    Ceic.logout()
    print(f"\nFetched {len(fetched)}/{len(targets)} series successfully.")

    if len(fetched) < len(targets):
        # Don't proceed with a partial swap — could leave the DB in a mixed state.
        sys.exit("Refusing to proceed with partial swap. Rerun once all 10 fetch successfully.")

    # ── 2. Stage scratch DB ─────────────────────────────────────────────
    print(f"\nStaging DB at {DB_SCRATCH}")
    if DB_SCRATCH.exists():
        DB_SCRATCH.unlink()
    journal = DB_SCRATCH.with_suffix(DB_SCRATCH.suffix + "-journal")
    if journal.exists():
        journal.unlink()
    shutil.copy(DB_LIVE, DB_SCRATCH)

    conn = sqlite3.connect(DB_SCRATCH)

    # ── 3. Wipe ALL existing rows for these series_ids (clears stale level data)
    placeholders = ",".join("?" for _ in fetched)
    n_deleted = conn.execute(
        f"DELETE FROM time_series WHERE series_id IN ({placeholders})",
        list(fetched.keys()),
    ).rowcount
    conn.commit()
    print(f"  Cleared {n_deleted} old level-index rows for the {len(fetched)} targets\n")

    # ── 4. Insert fresh YoY rows ────────────────────────────────────────
    total_inserted = 0
    for sid, (sdef, rows) in fetched.items():
        label = sdef.get("label", sid)
        unit = sdef.get("unit", "% YoY")
        frequency = sdef.get("frequency", "Monthly")
        conn.executemany(
            "INSERT OR REPLACE INTO time_series "
            "(date, value, series_id, series_name, source, unit, frequency, category) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, NULL)",
            [(d, v, sid, label, "ceic", unit, frequency) for d, v in rows],
        )
        total_inserted += len(rows)
    conn.commit()
    print(f"  Inserted {total_inserted} fresh YoY rows across {len(fetched)} series\n")

    # ── 5. Verify ────────────────────────────────────────────────────────
    print("=== Verification ===")
    for sid in sorted(fetched.keys()):
        r = conn.execute(
            "SELECT COUNT(*), MIN(date), MAX(date), unit "
            "FROM time_series WHERE series_id = ? "
            "GROUP BY unit",
            (sid,),
        ).fetchone()
        print(f"  {sid:<24s} | {r[0]:>4d} rows | {r[1]} → {r[2]} | unit={r[3]}")

    conn.close()

    # ── 6. Copy back ────────────────────────────────────────────────────
    print(f"\nCopying {DB_SCRATCH.name} → {DB_LIVE}")
    shutil.copy(DB_SCRATCH, DB_LIVE)
    print("\nDone. Run `python3.11 scripts/build_iran_monitor.py` to re-render.")


if __name__ == "__main__":
    main()
