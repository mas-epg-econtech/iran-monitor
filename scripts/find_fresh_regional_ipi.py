#!/usr/bin/env python3
"""
Find fresh CEIC activity / industrial-production series for countries whose
current Iran Monitor IPI series has gone stale.

Why this exists:
  - regional_ipi_cn (CEIC 371937157, "China Industrial Production Index 2010=100")
    stopped publishing in Nov 2022.
  - regional_ipi_id (CEIC 322957602, "Indonesia Industrial Production Index
    2010=100") last prints Dec 2025.
  Both render mostly empty in the war-period zoom (war start 28 Feb 2026).

What it does:
  For each (country, query) pair, calls Ceic.search() and then probes the top
  N hits via Ceic.series_data() to discover the latest observation date.
  Sorted output ranks candidates by freshness.

Run from Iran Monitor root with .env present:
  python3.11 scripts/find_fresh_regional_ipi.py
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


# Candidate searches per country. Each query is fed verbatim to Ceic.search().
# Keep the list short so the script doesn't hammer CEIC.
QUERIES: dict[str, list[str]] = {
    "China": [
        "China Industrial Production YoY",            # NBS publishes monthly YoY series — usually freshly updated
        "China Industrial Value Added YoY",
        "China VAI YoY Real",                          # CEIC's shorthand (VAI = Value Added of Industry)
        "China Manufacturing PMI",
        "China Industrial Production",
    ],
    "Indonesia": [
        "Indonesia IPI Manufacturing Total",
        "Indonesia Manufacturing Production Total",
        "Indonesia Large Medium Manufacturing",
        "Indonesia Industrial Production Index",
        "Indonesia Manufacturing PMI",
    ],
}

# Known-good ids to probe as a sanity check on the date-extraction logic.
# These are the existing Iran Monitor entries — we want to confirm the script
# correctly reports their (already-known) latest dates.
BENCHMARK_IDS: list[tuple[str, str]] = [
    ("regional_ipi_cn (current)", "371937157"),    # known stale: ends Nov 2022
    ("regional_ipi_id (current)", "322957602"),    # known stale: ends Dec 2025
    ("regional_ipi_jp (current)", "508465317"),    # known fresh: ends Feb 2026
    ("regional_ipi_tw (current)", "508241517"),    # known fresh: ends Mar 2026
]

PER_QUERY_LIMIT = 15        # how many results to scan per query
PROBE_TOP_N = 10            # of those, how many to probe for latest_date
SEARCH_TIMEOUT_SEC = 45
PROBE_TIMEOUT_SEC = 30


def _timeout_handler(signum, frame):
    raise TimeoutError("timed out")


def _safe_call(fn, timeout_sec: int):
    """Run fn() under a SIGALRM timeout. Returns (result, error)."""
    old = signal.signal(signal.SIGALRM, _timeout_handler)
    signal.alarm(timeout_sec)
    try:
        return fn(), None
    except Exception as exc:
        return None, exc
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old)


def fetch_latest_date(series_id: str) -> str | None:
    """Probe a series and return its latest observation date as YYYY-MM-DD.

    CEIC's time_points ordering is unreliable (sometimes reverse-chronological),
    so we take max() across every point's date string rather than indexing.
    """
    from ceic_api_client.pyceic import Ceic
    result, err = _safe_call(lambda: Ceic.series_data(str(series_id)), PROBE_TIMEOUT_SEC)
    if err or not result or not getattr(result, "data", None):
        return None
    tps = getattr(result.data[0], "time_points", []) or []
    if not tps:
        return None
    dates = []
    for tp in tps:
        raw = getattr(tp, "date", None)
        if raw:
            dates.append(str(raw)[:10])
    return max(dates) if dates else None


def search_one(query: str) -> list[dict]:
    """Return list of {id, name, country, freq, unit, status, source} dicts."""
    from ceic_api_client.pyceic import Ceic
    result, err = _safe_call(
        lambda: Ceic.search(query, limit=PER_QUERY_LIMIT),
        SEARCH_TIMEOUT_SEC,
    )
    if err:
        print(f"  SEARCH FAIL {query!r}: {err}")
        return []
    sd = result.data if hasattr(result, "data") else result
    items = getattr(sd, "items", []) or []
    out = []
    for item in items:
        meta = getattr(item, "metadata", None)
        if meta is None:
            continue
        out.append({
            # Coerce all fields to strings — CEIC returns id as int and any
            # of the *.name fields can be None.
            "id":      str(getattr(meta, "id", "?")),
            "name":    str(getattr(meta, "name", "?") or "?"),
            "country": str(getattr(getattr(meta, "country", None), "name", "?") or "?"),
            "freq":    str(getattr(getattr(meta, "frequency", None), "name", "?") or "?"),
            "unit":    str(getattr(getattr(meta, "unit", None), "name", "?") or "?"),
            "status":  str(getattr(getattr(meta, "status", None), "name", "?") or "?"),
            "source":  str(getattr(getattr(meta, "source", None), "name", "?") or "?"),
        })
    return out


def main() -> None:
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

    # ── 0. Sanity-check the date probe against known-good ids ──────────
    print("=" * 70)
    print("  BENCHMARK PROBE — sanity check on date-extraction")
    print("=" * 70)
    for label, sid in BENCHMARK_IDS:
        latest = fetch_latest_date(sid)
        print(f"  {label:<32s} id={sid:<12s} latest={latest}")
    print()

    all_candidates: list[dict] = []     # gather across all (country, query) pairs

    for country, queries in QUERIES.items():
        print(f"{'='*70}")
        print(f"  {country}")
        print(f"{'='*70}")
        seen_ids: set[str] = set()
        for q in queries:
            print(f"  -> search {q!r}")
            results = search_one(q)
            print(f"     got {len(results)} hits")
            for r in results[:PROBE_TOP_N]:
                if r["id"] in seen_ids:
                    continue
                seen_ids.add(r["id"])
                latest = fetch_latest_date(r["id"])
                r["latest_date"] = latest or "?"
                r["country_query"] = country
                r["search_query"] = q
                all_candidates.append(r)
                print(
                    f"     {r['id']:<12s}  latest={r['latest_date']:<10s}  "
                    f"freq={r['freq']:<10s}  status={r['status']:<10s}  "
                    f"unit={r['unit']:<25s}  {r['name'][:80]}"
                )
        print()

    # ── Ranked summary by freshness, per country ────────────────────────
    print()
    print("=" * 70)
    print("  RANKED RESULTS (most recent first, per country)")
    print("=" * 70)
    for country in QUERIES:
        rows = [c for c in all_candidates if c["country_query"] == country]
        rows.sort(key=lambda c: c.get("latest_date") or "", reverse=True)
        print(f"\n## {country} — top 10 by latest_date")
        for r in rows[:10]:
            print(f"  {r['latest_date']:<10s}  id={r['id']:<12s}  "
                  f"freq={r['freq']:<10s}  status={r['status']:<10s}  "
                  f"{r['name'][:90]}")

    Ceic.logout()
    print("\nDone. Pick the freshest published series and update SERIES_REGISTRY.")


if __name__ == "__main__":
    main()
