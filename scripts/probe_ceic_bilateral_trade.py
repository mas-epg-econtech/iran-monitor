#!/usr/bin/env python3
"""
CEIC discovery probe — does CEIC have bilateral trade × commodity data
fresh enough to fill the 2025 coverage gap that's blocking the Comtrade
SITC-Annual ingestor?

What we need (per regional reporter):
  - Annual chemical imports from Singapore  (numerator for SG-dependence ratio)
  - Annual chemical imports from World      (denominator)
  - Annual mineral fuel imports from each ME country  (numerator for ME exposure)
  - Annual mineral fuel imports from World            (denominator)

The shape: bilateral × commodity × annual. CEIC's *aggregate* trade data
is widely available, but bilateral × commodity coverage is patchier.

What this probe does:
  For each of the 10 regional reporters, run several search queries that
  might surface bilateral × commodity series. For each hit, print:
    - Series ID, name, frequency, unit
    - Whether the series is part of our subscription
    - Latest period available (rough freshness check)

  Goal: identify which (reporter, dataset) combinations CEIC has, so we
  can build a mosaic-fetch strategy if Comtrade HS doesn't fill the gap.

Run:
  python3.11 scripts/probe_ceic_bilateral_trade.py
"""
from __future__ import annotations

import os
import signal
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


_ROOT = Path(__file__).resolve().parent.parent
_load_env(_ROOT / ".env")
_load_env(Path("/Users/kevinlim/Documents/MAS/Projects/ESD/Middle East Dashboard/.env"))


# 10 regional reporters. We name them for the queries — not their ISO codes.
REGIONAL_REPORTERS = [
    "China",
    "India",
    "Indonesia",
    "Japan",
    "Korea",       # CEIC indexes as "Korea" (sometimes "Korea, Republic of")
    "Malaysia",
    "Philippines",
    "Taiwan",
    "Thailand",
    "Vietnam",
]

# Search queries — try several phrasings since CEIC uses different
# vocabulary across reporter datasets ("by Country", "by Partner",
# "Direction", "Origin").
QUERY_TEMPLATES = [
    "{reporter} Imports by Country and Commodity",
    "{reporter} Imports by SITC by Country",
    "{reporter} Imports by Partner Country Chemical",
    "{reporter} Imports Singapore Chemical",
    "{reporter} Imports Origin SITC",
]

# Cap results per query to keep the output digestible. Search up to 10
# results — we just want a yes/no on whether the series exists.
MAX_RESULTS_PER_QUERY = 10


def _timeout_handler(signum, frame):
    raise TimeoutError("timed out")


def search_one(query: str, max_results: int = MAX_RESULTS_PER_QUERY):
    """One CEIC search call with a 45s timeout. Returns list of (id, name,
    country, freq, unit, source, subscribed, latest_obs_period_str) tuples."""
    from ceic_api_client.pyceic import Ceic

    old = signal.signal(signal.SIGALRM, _timeout_handler)
    signal.alarm(45)

    out = []
    try:
        result = Ceic.search(query, limit=max_results)
        signal.alarm(0)
        sd = result.data if hasattr(result, "data") else result
        items = getattr(sd, "items", []) or []
        for item in items:
            meta = getattr(item, "metadata", None)
            if meta is None:
                continue
            sid = getattr(meta, "id", "?")
            name = getattr(meta, "name", "?")
            freq_obj = getattr(meta, "frequency", None)
            freq = getattr(freq_obj, "name", "?") if freq_obj else "?"
            unit_obj = getattr(meta, "unit", None)
            unit = getattr(unit_obj, "name", "?") if unit_obj else "?"
            country_obj = getattr(meta, "country", None)
            country = getattr(country_obj, "name", "?") if country_obj else "?"
            source_obj = getattr(meta, "source", None)
            source = getattr(source_obj, "name", "?") if source_obj else "?"
            subscribed = bool(getattr(item, "subscribed", False))
            # Try to get latest observation date if present in metadata
            last_period = ""
            try:
                last_period = str(getattr(meta, "last_update_time", "") or "")
            except Exception:
                pass
            out.append((sid, name, country, freq, unit, source, subscribed, last_period))
    except TimeoutError:
        signal.alarm(0)
    except Exception as exc:
        signal.alarm(0)
        print(f"     ERROR: {exc}")
    finally:
        signal.signal(signal.SIGALRM, old)
    return out


def main() -> None:
    try:
        from ceic_api_client.pyceic import Ceic
    except ImportError:
        sys.exit("ceic_api_client not installed for this Python interpreter.")

    username = os.environ.get("CEIC_USERNAME", "")
    password = os.environ.get("CEIC_PASSWORD", "")
    if not username or not password:
        sys.exit("Set CEIC_USERNAME and CEIC_PASSWORD (in Iran Monitor/.env).")

    print(f"Logging in as {username}...")
    Ceic.login(username, password)
    print("Login OK\n")

    # Per-reporter aggregate counters: how many hits matched ANY query?
    summary: dict[str, dict] = {}

    for reporter in REGIONAL_REPORTERS:
        print(f"\n{'=' * 78}")
        print(f"  REPORTER: {reporter}")
        print(f"{'=' * 78}")

        all_hits = []   # list of (query, hit_tuple)
        for tmpl in QUERY_TEMPLATES:
            q = tmpl.format(reporter=reporter)
            hits = search_one(q)
            print(f"  [{len(hits)} hits] {q!r}")
            for h in hits:
                all_hits.append((q, h))

        # Filter to only series that look like bilateral × commodity (rough
        # heuristic — keep series whose name contains both a partner-flavor
        # word AND a commodity-flavor word). Keeps the report focused.
        partner_words   = ("Country", "Partner", "Origin", "Singapore", "Direction")
        commodity_words = ("SITC", "HS", "Chemical", "Commodity", "Mineral", "Petroleum", "Fuel", "Chapter")
        filtered = []
        for q, (sid, name, country, freq, unit, source, sub, lp) in all_hits:
            n = (name or "")
            if any(w in n for w in partner_words) and any(w in n for w in commodity_words):
                filtered.append((q, sid, name, country, freq, unit, source, sub, lp))

        # Dedupe by series id
        seen_ids = set()
        deduped = []
        for row in filtered:
            sid = row[1]
            if sid in seen_ids:
                continue
            seen_ids.add(sid)
            deduped.append(row)

        print(f"\n  Filtered candidates ({len(deduped)} unique, partner+commodity heuristic):")
        if not deduped:
            print("    [none — no bilateral × commodity series matched a query]")
        else:
            # Print at most 8 per reporter to keep output readable
            for q, sid, name, country, freq, unit, source, sub, lp in deduped[:8]:
                tag = " [SUBSCRIBED]" if sub else ""
                print(f"    {sid}  {name[:90]}{tag}")
                print(f"       country={country}  freq={freq}  unit={unit}  src={source}")
                if lp:
                    print(f"       latest={lp}")
            if len(deduped) > 8:
                print(f"    ... and {len(deduped) - 8} more (truncated)")

        summary[reporter] = {
            "total_hits": len(all_hits),
            "candidates": len(deduped),
            "subscribed_candidates": sum(1 for r in deduped if r[7]),
        }

    # ── Final cross-reporter summary table ───────────────────────────────
    print(f"\n{'=' * 78}")
    print("  SUMMARY — bilateral × commodity series candidates per reporter")
    print(f"{'=' * 78}")
    print(f"  {'Reporter':<14s} {'all hits':>10s} {'candidates':>14s} {'subscribed':>12s}")
    print(f"  {'-'*14} {'-'*10} {'-'*14} {'-'*12}")
    for reporter, s in summary.items():
        print(f"  {reporter:<14s} {s['total_hits']:>10} {s['candidates']:>14} "
              f"{s['subscribed_candidates']:>12}")

    Ceic.logout()
    print("\nDone.")
    print("Note: 'candidates' is filtered by a rough name heuristic")
    print("(partner-word + commodity-word). Manual inspection still needed.")


if __name__ == "__main__":
    main()
