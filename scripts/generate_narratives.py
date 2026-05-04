#!/usr/bin/env python3
"""
Iran Monitor — LLM narrative orchestrator.

Loads the four prompt templates from `prompts/`, slices the relevant page
data from `data/summary_stats.json`, calls Claude Sonnet 4.6 four times
(three page-level + one synthesizer), parses the JSON outputs, and stores
them in the metadata table for the renderer to consume.

Usage:
    python3 scripts/generate_narratives.py            # uses live API
    python3 scripts/generate_narratives.py --dry-run  # prints prompts only
    python3 scripts/generate_narratives.py --pages global_shocks,singapore
                                                       # only run a subset
    python3 scripts/generate_narratives.py --out data/narratives.json
                                                       # write outputs to JSON
                                                       # (default: also stash in DB metadata)

Requires `ANTHROPIC_API_KEY` in `.env`. Charges ~$0.30-1.00 per full run
(four Sonnet 4.6 calls; bulk of cost is the page-level summary-stats input).
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.db import get_connection  # type: ignore  # noqa: E402

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
PROMPTS_DIR    = ROOT / "prompts"
STATS_PATH     = ROOT / "data" / "summary_stats.json"
NARRATIVES_OUT = ROOT / "data" / "narratives.json"

# Anthropic Sonnet 4.6 — chosen for all four calls per the design.
MODEL          = "claude-sonnet-4-6"
MAX_TOKENS_OUT = 4096      # page outputs ~1.5KB; synthesizer ~2KB; 4096 is safe
TEMPERATURE    = 0.0       # we want stable, reproducible reads

# Pages we run page-level prompts for, and the slug we write to in the DB.
PAGE_KEYS = ["global_shocks", "singapore", "regional"]


# ---------------------------------------------------------------------------
# Prompt parsing — markdown frontmatter + System / User sections
# ---------------------------------------------------------------------------
def _parse_prompt_file(path: Path) -> dict:
    """Parse a prompt file into {frontmatter, system, user_template}.

    Format:
        ---
        <YAML frontmatter>
        ---

        # System

        <system prompt body>

        # User

        <user prompt template, with {{var}} placeholders>
    """
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise ValueError(f"{path.name}: missing YAML frontmatter")
    _, fm_block, body = text.split("---", 2)
    # Cheap YAML-ish parse: prompt files only use simple key:value + bullet lists,
    # so we don't pull in PyYAML for one config block. Falls through gracefully.
    frontmatter: dict = {}
    cur_list_key: str | None = None
    for line in fm_block.strip().splitlines():
        if line.strip().startswith("#"):
            continue
        if line.startswith("  - "):
            if cur_list_key:
                frontmatter.setdefault(cur_list_key, []).append(line[4:].split("#")[0].strip())
            continue
        if ":" in line:
            key, _, val = line.partition(":")
            key = key.strip()
            val = val.split("#")[0].strip()
            if val:
                frontmatter[key] = val
                cur_list_key = None
            else:
                cur_list_key = key
                frontmatter[key] = []

    # Split System / User. Headers are markdown level-1 (#) followed by name.
    sys_marker = body.find("# System")
    usr_marker = body.find("# User")
    if sys_marker < 0 or usr_marker < 0:
        raise ValueError(f"{path.name}: must contain '# System' and '# User' headers")
    system_text = body[sys_marker + len("# System"):usr_marker].strip()
    user_text   = body[usr_marker + len("# User"):].strip()
    return {
        "name":          frontmatter.get("prompt_name", path.stem),
        "frontmatter":   frontmatter,
        "system":        system_text,
        "user_template": user_text,
    }


def _substitute(template: str, mapping: dict[str, str]) -> str:
    """Replace `{{key}}` tokens with values from mapping. Missing keys raise."""
    out = template
    for k, v in mapping.items():
        out = out.replace("{{" + k + "}}", v)
    # Detect any unsubstituted placeholders.
    import re
    leftover = re.findall(r"\{\{(\w+)\}\}", out)
    if leftover:
        raise ValueError(f"Unsubstituted template variables: {leftover}")
    return out


# ---------------------------------------------------------------------------
# Stats slicing — give each page-level prompt only its own data
# ---------------------------------------------------------------------------
def _slice_for_page(stats: dict, page_slug: str) -> dict:
    """Build a page-only slice of summary_stats.json, including the relevance
    index restricted to this page so the LLM can quickly enumerate its
    in-scope chart_ids without scanning the full tree."""
    if page_slug not in stats:
        raise KeyError(f"Page slug '{page_slug}' not in stats")

    full_meta = stats.get("_meta", {})
    by_relevance = full_meta.get("charts_by_relevance", {})

    # Restrict the relevance index to this page only.
    page_relevance: dict[str, list[str]] = {}
    for tag, by_page in by_relevance.items():
        if page_slug in by_page:
            page_relevance[tag] = by_page[page_slug]

    sliced_meta = {
        "as_of_date":         full_meta.get("as_of_date"),
        "baseline":           full_meta.get("baseline"),
        "charts_by_relevance": {page_slug: page_relevance},
    }

    return {
        "_meta":   sliced_meta,
        page_slug: stats[page_slug],
    }


# ---------------------------------------------------------------------------
# Anthropic API
# ---------------------------------------------------------------------------
def _call_anthropic(system: str, user: str, dry_run: bool = False) -> tuple[str, dict]:
    """Send one (system, user) pair to Sonnet 4.6 and return (raw_text, meta).
    `meta` records token usage + latency. In dry-run mode, returns the prompt
    text concatenated and a synthetic empty meta — no API call is made."""
    if dry_run:
        return ("[DRY-RUN — no API call made]\n"
                f"--- SYSTEM ({len(system)} chars) ---\n{system[:200]}...\n"
                f"--- USER ({len(user)} chars) ---\n{user[:200]}...\n"), {}

    try:
        from anthropic import Anthropic
    except ImportError:
        sys.exit("anthropic package not installed. Run: pip install anthropic")

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        sys.exit("ANTHROPIC_API_KEY not set in environment / .env")

    client = Anthropic(api_key=api_key)
    t0 = time.time()
    resp = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS_OUT,
        temperature=TEMPERATURE,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    elapsed = time.time() - t0

    # Extract the text content (single text block per message).
    text = ""
    for block in resp.content:
        if getattr(block, "type", None) == "text":
            text += block.text
    meta = {
        "model":           resp.model,
        "stop_reason":     resp.stop_reason,
        "input_tokens":    resp.usage.input_tokens,
        "output_tokens":   resp.usage.output_tokens,
        "elapsed_sec":     round(elapsed, 2),
    }
    return text, meta


# ---------------------------------------------------------------------------
# JSON parsing — defensive against fence wrapping
# ---------------------------------------------------------------------------
def _parse_json_response(text: str) -> dict:
    """Parse the LLM's response as JSON. Strips markdown fences if present
    despite our explicit instruction not to use them."""
    s = text.strip()
    # Strip ```json ... ``` fences if the model decided to add them anyway.
    if s.startswith("```"):
        # Remove first line (```json or ```) and trailing fence
        first_nl = s.find("\n")
        s = s[first_nl + 1 :] if first_nl >= 0 else s
        if s.endswith("```"):
            s = s[: -3]
        s = s.strip()
    return json.loads(s)


# ---------------------------------------------------------------------------
# Persistence — store each output under a metadata key
# ---------------------------------------------------------------------------
def _store_output(conn: sqlite3.Connection, key: str, payload: dict) -> None:
    """Stash the full JSON payload under one metadata key. We embed the
    timestamp inside the JSON value (the metadata table is just key/value
    in this DB)."""
    conn.execute(
        "INSERT OR REPLACE INTO metadata(key, value) VALUES (?, ?)",
        (key, json.dumps({"updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                          "payload":    payload}, ensure_ascii=False)),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true",
                   help="Skip API calls — print prompts and exit.")
    p.add_argument("--pages", default=",".join(PAGE_KEYS) + ",synthesizer",
                   help="Comma-separated subset to run "
                        "(default: all 4 — three page calls + synthesizer).")
    p.add_argument("--out", default=str(NARRATIVES_OUT),
                   help=f"Output file for collected narratives "
                        f"(default: {NARRATIVES_OUT.relative_to(ROOT)}).")
    p.add_argument("--no-db", action="store_true",
                   help="Skip writing to metadata table; file only.")
    args = p.parse_args()

    requested = [s.strip() for s in args.pages.split(",") if s.strip()]
    valid     = set(PAGE_KEYS + ["synthesizer"])
    bad       = [r for r in requested if r not in valid]
    if bad:
        sys.exit(f"Unknown pages: {bad}. Valid: {sorted(valid)}")

    # Load environment + summary stats
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    if not STATS_PATH.exists():
        sys.exit(f"Summary stats not found: {STATS_PATH}\n"
                 "Run scripts/compute_summary_stats.py first.")
    stats = json.loads(STATS_PATH.read_text(encoding="utf-8"))
    as_of_date     = stats["_meta"]["as_of_date"]
    baseline_label = stats["_meta"]["baseline"]["label"]

    print(f"=== narrative orchestrator — as_of {as_of_date} ===")
    print(f"  baseline: {baseline_label}")
    print(f"  model:    {MODEL}")
    print(f"  pages:    {requested}")
    if args.dry_run:
        print("  ⚠️  DRY-RUN — no API calls")
    print()

    # Run each page-level prompt
    page_outputs: dict[str, dict] = {}
    total_in_tokens  = 0
    total_out_tokens = 0
    for page in PAGE_KEYS:
        if page not in requested:
            continue
        prompt_path = PROMPTS_DIR / f"{page}.md"
        if not prompt_path.exists():
            sys.exit(f"Prompt file missing: {prompt_path}")
        prompt = _parse_prompt_file(prompt_path)

        page_stats = _slice_for_page(stats, page)
        user_msg = _substitute(prompt["user_template"], {
            "as_of_date":         as_of_date,
            "baseline_label":     baseline_label,
            "page_summary_stats": json.dumps(page_stats, ensure_ascii=False, indent=2),
        })
        print(f"[{page}] system={len(prompt['system']):,} chars · user={len(user_msg):,} chars")

        text, meta = _call_anthropic(prompt["system"], user_msg, dry_run=args.dry_run)
        if args.dry_run:
            print(text[:400])
            print("  ...")
            continue
        try:
            output = _parse_json_response(text)
        except json.JSONDecodeError as e:
            print(f"[{page}] ❌ JSON parse failed: {e}")
            print(f"--- raw response ---\n{text[:1500]}")
            sys.exit(1)

        page_outputs[page] = output
        total_in_tokens  += meta["input_tokens"]
        total_out_tokens += meta["output_tokens"]
        print(f"  → tokens: {meta['input_tokens']:,} in / {meta['output_tokens']:,} out · "
              f"{meta['elapsed_sec']}s · stop={meta['stop_reason']}")
        # Checkpoint after every successful page call so partial progress
        # survives interruption (long Anthropic calls can exceed sandbox
        # timeouts; resuming should be possible without re-running successful
        # calls).
        ckpt_path = Path(args.out)
        ckpt_path.parent.mkdir(parents=True, exist_ok=True)
        partial_bundle = {
            "as_of_date":     as_of_date,
            "baseline_label": baseline_label,
            "model":          MODEL,
            "pages":          page_outputs,
            "synthesizer":    None,
            "complete":       False,
        }
        ckpt_path.write_text(json.dumps(partial_bundle, ensure_ascii=False, indent=2),
                              encoding="utf-8")

    # Run synthesizer (only if all 3 page outputs are present and synth requested)
    synth_output = None
    if "synthesizer" in requested and not args.dry_run:
        # If page outputs weren't generated this run (e.g. `--pages synthesizer`),
        # load them from the DB metadata table (canonical store) so
        # synthesizer-only reruns work without re-running the page calls.
        # Fall back to the bundle file if the DB doesn't have them.
        if any(p not in page_outputs for p in PAGE_KEYS):
            try:
                _conn = get_connection()
                for p in PAGE_KEYS:
                    if p in page_outputs:
                        continue
                    row = _conn.execute(
                        "SELECT value FROM metadata WHERE key = ?",
                        (f"narrative_{p}",),
                    ).fetchone()
                    if row and row["value"]:
                        wrapped = json.loads(row["value"])
                        # Stored as {"updated_at": ..., "payload": ...}
                        page_outputs[p] = wrapped.get("payload", wrapped)
                        print(f"  ↺ loaded {p} from DB metadata")
                _conn.close()
            except Exception as e:
                print(f"  ⚠️  could not load page outputs from DB: {e}")

        if any(p not in page_outputs for p in PAGE_KEYS):
            existing_bundle_path = Path(args.out)
            if existing_bundle_path.exists():
                try:
                    existing = json.loads(existing_bundle_path.read_text(encoding="utf-8"))
                    existing_pages = existing.get("pages") or {}
                    for p in PAGE_KEYS:
                        if p not in page_outputs and p in existing_pages and existing_pages[p]:
                            page_outputs[p] = existing_pages[p]
                            print(f"  ↺ loaded {p} from existing bundle")
                except (json.JSONDecodeError, OSError) as e:
                    print(f"  ⚠️  could not reuse existing bundle: {e}")

        if any(p not in page_outputs for p in PAGE_KEYS):
            missing = [p for p in PAGE_KEYS if p not in page_outputs]
            print(f"\n⚠️  Skipping synthesizer — missing page outputs: {missing}")
        else:
            prompt_path = PROMPTS_DIR / "synthesizer.md"
            prompt = _parse_prompt_file(prompt_path)
            user_msg = _substitute(prompt["user_template"], {
                "as_of_date":           as_of_date,
                "global_shocks_output": json.dumps(page_outputs["global_shocks"], ensure_ascii=False, indent=2),
                "singapore_output":     json.dumps(page_outputs["singapore"],     ensure_ascii=False, indent=2),
                "regional_output":      json.dumps(page_outputs["regional"],      ensure_ascii=False, indent=2),
            })
            print(f"\n[synthesizer] system={len(prompt['system']):,} chars · user={len(user_msg):,} chars")
            text, meta = _call_anthropic(prompt["system"], user_msg)
            try:
                synth_output = _parse_json_response(text)
            except json.JSONDecodeError as e:
                print(f"[synthesizer] ❌ JSON parse failed: {e}")
                print(f"--- raw response ---\n{text[:1500]}")
                sys.exit(1)
            total_in_tokens  += meta["input_tokens"]
            total_out_tokens += meta["output_tokens"]
            print(f"  → tokens: {meta['input_tokens']:,} in / {meta['output_tokens']:,} out · "
                  f"{meta['elapsed_sec']}s · stop={meta['stop_reason']}")

    if args.dry_run:
        return

    # Persist final bundle (overwrites any incremental checkpoints from above).
    bundle = {
        "as_of_date":      as_of_date,
        "baseline_label":  baseline_label,
        "model":           MODEL,
        "pages":           page_outputs,
        "synthesizer":     synth_output,
        "complete":        synth_output is not None or "synthesizer" not in requested,
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✅ Wrote {out_path.relative_to(ROOT) if out_path.is_relative_to(ROOT) else out_path}")

    if not args.no_db:
        conn = get_connection()
        try:
            for page, output in page_outputs.items():
                _store_output(conn, f"narrative_{page}", output)
            if synth_output is not None:
                _store_output(conn, "narrative_synthesizer", synth_output)
            print(f"  Stored in DB metadata table.")

            # Save the trigger snapshot — captures the indicator state at
            # narrative-generation time so the next run's trigger evaluator
            # can detect whether anything has moved enough to warrant a
            # fresh narrative. Best-effort: a missing trigger config is
            # not fatal.
            try:
                from src.narrative_triggers_v2 import (   # type: ignore
                    load_thresholds, save_snapshot,
                )
                thresholds = load_thresholds()
                snapshot = save_snapshot(conn, stats, thresholds)
                print(f"  Saved trigger snapshot ({len(snapshot.get('series', {}))} series).")
            except FileNotFoundError as e:
                print(f"  ⚠️  Trigger snapshot skipped: {e}")
            except Exception as e:
                print(f"  ⚠️  Trigger snapshot failed (non-fatal): {e}")
        finally:
            conn.close()

    # Cost back-of-envelope. Sonnet 4.6 pricing as of mid-2026:
    # input $3/M, output $15/M.
    cost_in  = total_in_tokens  / 1_000_000 * 3.0
    cost_out = total_out_tokens / 1_000_000 * 15.0
    print(f"\n=== usage ===")
    print(f"  total tokens: {total_in_tokens:,} in / {total_out_tokens:,} out")
    print(f"  est cost:     ${cost_in + cost_out:.3f}  (in ${cost_in:.3f} + out ${cost_out:.3f})")


if __name__ == "__main__":
    main()
