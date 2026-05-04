#!/usr/bin/env python3
"""
Iran Monitor — one-shot seed for the narrative trigger snapshot.

Reads `data/summary_stats.json` and saves a trigger snapshot to the DB
metadata table without making any LLM calls. Run this once after rolling
out the trigger system, so the next `update_data.py` run can gate
properly instead of forcing a first-run refresh.

The snapshot's `narrative_generated_at` defaults to "now" — meaning the
7-day max-age floor restarts from this moment, which assumes the
narratives currently in the DB are reasonably fresh. Pass an explicit
`--narrative-generated-at <iso8601>` to override.

Usage:
    python3 scripts/seed_trigger_snapshot.py
    python3 scripts/seed_trigger_snapshot.py --narrative-generated-at 2026-05-01T15:05:00Z
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.db import get_connection                    # noqa: E402
from src.narrative_triggers_v2 import (              # noqa: E402
    SNAPSHOT_KEY, build_snapshot, load_thresholds,
)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--narrative-generated-at",
        default=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        help="ISO 8601 timestamp recorded as the narrative-generation time "
             "in the snapshot. Defaults to now (assumes the narratives "
             "currently in the DB are fresh).",
    )
    args = p.parse_args()

    stats_path = ROOT / "data" / "summary_stats.json"
    if not stats_path.exists():
        sys.exit(f"summary_stats.json not found: {stats_path}\n"
                 f"Run scripts/compute_summary_stats.py first.")
    stats = json.loads(stats_path.read_text(encoding="utf-8"))

    thresholds = load_thresholds()

    snapshot = build_snapshot(stats, thresholds, args.narrative_generated_at)

    conn = get_connection()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO metadata(key, value) VALUES (?, ?)",
            (SNAPSHOT_KEY, json.dumps(snapshot, ensure_ascii=False)),
        )
        conn.commit()
    finally:
        conn.close()

    print(f"Seeded trigger snapshot ({len(snapshot.get('series', {}))} series)")
    print(f"  narrative_generated_at = {args.narrative_generated_at}")
    print(f"  next run gates against this state")


if __name__ == "__main__":
    main()
