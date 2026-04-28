#!/usr/bin/env python3
"""
Generate or regenerate the LLM narrative independently of the data pipeline.

Usage:
    python scripts/generate_narrative.py           # only if triggers fire
    python scripts/generate_narrative.py --force    # regenerate regardless
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.db import get_metadata, upsert_metadata
from build_dashboard import export_time_series, compute_summary
from src.narrative_triggers import evaluate_triggers


def load_env():
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def main():
    load_env()
    force = "--force" in sys.argv

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY not set in .env")
        sys.exit(1)

    print("Computing summary stats...")
    series_data = export_time_series()
    current_stats = compute_summary(series_data)

    if not force:
        prev_stats_json = get_metadata("narrative_prev_stats")
        prev_timestamp = get_metadata("narrative_generated_at")
        prev_stats = json.loads(prev_stats_json) if prev_stats_json else None

        fired = evaluate_triggers(current_stats, prev_stats, prev_timestamp)
        if not fired:
            print("No triggers fired. Use --force to regenerate anyway.")
            existing = get_metadata("llm_narrative")
            if existing:
                print(f"\nCurrent narrative ({len(existing)} chars):")
                print(existing)
            return

        print(f"{len(fired)} trigger(s) fired:")
        for t in fired:
            print(f"  - {t.id}: {t.description}")
    else:
        print("Force mode — skipping trigger check")

    # Import here so script works even without anthropic if just checking triggers
    import anthropic
    from src.narrative_prompt import NARRATIVE_PROMPT

    print("\nCalling Claude API...")
    client = anthropic.Anthropic(api_key=api_key)
    stats_json = json.dumps(current_stats, indent=2)
    prompt = NARRATIVE_PROMPT.format(stats_json=stats_json)

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )

    narrative = message.content[0].text.strip()

    gen_timestamp = datetime.now(timezone.utc).isoformat()
    upsert_metadata("llm_narrative", narrative)
    upsert_metadata("narrative_prev_stats", json.dumps(current_stats))
    upsert_metadata("narrative_generated_at", gen_timestamp)
    upsert_metadata("narrative_triggers_fired", "force" if force else ", ".join(t.id for t in fired))

    print(f"\nNarrative generated ({len(narrative)} chars):")
    print(narrative)
    print(f"\nStored at {gen_timestamp}")


if __name__ == "__main__":
    main()
