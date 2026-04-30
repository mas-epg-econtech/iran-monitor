#!/usr/bin/env python3
"""
CEIC audit: best real-side activity measure for the 10 regional countries.

Goal: find one CEIC measure family that's fresh and consistent across all 10
Asian economies on the Iran Monitor regional page (CN, IN, ID, JP, MY, PH,
KR, TW, TH, VN). The current per-country IPI level approach has stale data
for CN (Nov 2022) and ID (Dec 2025); this audit scans alternatives.

What it does:
  For each (country, measure_family) combination:
    1. Run 1-3 search queries against CEIC.
    2. Dedupe by series id, probe top N for latest observation date.
    3. Record candidates in a global pool.

  Then emit three reports:
    A) Per-(country, family) ranked list
    B) Best-candidate-per-country, per family — picks the freshest hit per
       country and ranks countries by data lag.
    C) Coverage summary: how many of the 10 countries have fresh data per
       family — answers "is there a single measure that works for all 10?".

Run from Iran Monitor root with .env present:
  python3.11 scripts/audit_regional_activity_ceic.py

Output is verbose; save to a file:
  python3.11 scripts/audit_regional_activity_ceic.py | tee /tmp/ceic_audit.txt
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


# ── Configuration ────────────────────────────────────────────────────────
COUNTRIES = [
    "China", "India", "Indonesia", "Japan", "Malaysia",
    "Philippines", "South Korea", "Taiwan", "Thailand", "Vietnam",
]

# (family_name, [query_template, ...]) — {country} placeholder is substituted.
MEASURE_FAMILIES: list[tuple[str, list[str]]] = [
    ("Manufacturing PMI", [
        "{country} Manufacturing PMI",
        "{country} PMI Manufacturing",
        "{country} S&P Global Manufacturing PMI",
    ]),
    ("IPI YoY %", [
        "{country} Industrial Production YoY",
        "{country} Manufacturing Production YoY",
        "{country} Industrial Production Index YoY",
    ]),
    ("IPI Level", [
        "{country} Industrial Production Index",
        "{country} Manufacturing Production Index",
    ]),
]

PER_QUERY_LIMIT = 10
PROBE_TOP_N     = 5         # probe this many top hits per query for freshness
SEARCH_TIMEOUT  = 45
PROBE_TIMEOUT   = 30


# ── CEIC helpers ─────────────────────────────────────────────────────────
def _timeout_handler(signum, frame):
    raise TimeoutError("timed out")


def _safe_call(fn, timeout_sec: int):
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
    """Probe a series — return its latest observation as YYYY-MM-DD, or None.
    Uses max() across all time_points (CEIC ordering isn't reliable)."""
    from ceic_api_client.pyceic import Ceic
    result, err = _safe_call(lambda: Ceic.series_data(str(series_id)), PROBE_TIMEOUT)
    if err or not result or not getattr(result, "data", None):
        return None
    tps = getattr(result.data[0], "time_points", []) or []
    dates = []
    for tp in tps:
        raw = getattr(tp, "date", None)
        if raw:
            dates.append(str(raw)[:10])
    return max(dates) if dates else None


def search_one(query: str) -> list[dict]:
    """Search CEIC for a single query string. Returns list of metadata dicts."""
    from ceic_api_client.pyceic import Ceic
    result, err = _safe_call(
        lambda: Ceic.search(query, limit=PER_QUERY_LIMIT),
        SEARCH_TIMEOUT,
    )
    if err:
        print(f"     SEARCH FAIL: {err}")
        return []
    sd = result.data if hasattr(result, "data") else result
    items = getattr(sd, "items", []) or []
    out = []
    for item in items:
        meta = getattr(item, "metadata", None)
        if meta is None:
            continue
        out.append({
            "id":      str(getattr(meta, "id", "?")),
            "name":    str(getattr(meta, "name", "?") or "?"),
            "country": str(getattr(getattr(meta, "country", None), "name", "?") or "?"),
            "freq":    str(getattr(getattr(meta, "frequency", None), "name", "?") or "?"),
            "unit":    str(getattr(getattr(meta, "unit", None), "name", "?") or "?"),
            "status":  str(getattr(getattr(meta, "status", None), "name", "?") or "?"),
            "source":  str(getattr(getattr(meta, "source", None), "name", "?") or "?"),
        })
    return out


# ── Main audit loop ──────────────────────────────────────────────────────
def main() -> None:
    try:
        from ceic_api_client.pyceic import Ceic
    except ImportError:
        sys.exit("ceic_api_client not installed for this Python interpreter.")

    user = os.environ.get("CEIC_USERNAME", "")
    pwd = os.environ.get("CEIC_PASSWORD", "")
    if not user or not pwd:
        sys.exit("CEIC_USERNAME / CEIC_PASSWORD not set.")

    print(f"Logging in as {user}...")
    Ceic.login(user, pwd)
    print("Login OK\n")

    # Pool: list of dicts with all fields + family + country_query + latest_date
    pool: list[dict] = []

    for country in COUNTRIES:
        for family, query_templates in MEASURE_FAMILIES:
            print(f"{'─'*72}")
            print(f"  {country}  /  {family}")
            print(f"{'─'*72}")
            seen_ids: set[str] = set()
            for tmpl in query_templates:
                query = tmpl.format(country=country)
                print(f"  -> {query!r}")
                results = search_one(query)
                if not results:
                    print(f"     (no hits)")
                    continue
                # Probe top N (deduplicated by id)
                probed_in_this_query = 0
                for r in results:
                    if r["id"] in seen_ids:
                        continue
                    if probed_in_this_query >= PROBE_TOP_N:
                        break
                    seen_ids.add(r["id"])
                    latest = fetch_latest_date(r["id"])
                    r["latest_date"]    = latest or "?"
                    r["country_query"]  = country
                    r["family"]         = family
                    r["search_query"]   = query
                    pool.append(r)
                    probed_in_this_query += 1
                    print(
                        f"     {r['id']:<12s} {r['latest_date']:<10s} "
                        f"freq={r['freq']:<10s} unit={r['unit'][:18]:<18s} "
                        f"src={r['source'][:14]:<14s} {r['name'][:60]}"
                    )

    Ceic.logout()

    # ── Report A: per-(country, family) top 5 by freshness ──────────────
    print()
    print("=" * 72)
    print("  REPORT A — Top 5 candidates per (country, family), by freshness")
    print("=" * 72)
    for country in COUNTRIES:
        for family, _ in MEASURE_FAMILIES:
            rows = [c for c in pool if c["country_query"] == country and c["family"] == family]
            rows.sort(key=lambda c: c.get("latest_date") or "", reverse=True)
            if not rows:
                continue
            print(f"\n  ## {country}  /  {family}")
            for r in rows[:5]:
                print(f"     {r['latest_date']:<10s} id={r['id']:<12s} "
                      f"freq={r['freq']:<10s} unit={r['unit'][:18]:<18s} "
                      f"src={r['source'][:14]:<14s} {r['name'][:70]}")

    # ── Report B: best candidate per country, grouped by family ─────────
    # For each family, show the freshest series per country.
    print()
    print("=" * 72)
    print("  REPORT B — Best (freshest) candidate per country, per family")
    print("=" * 72)
    for family, _ in MEASURE_FAMILIES:
        print(f"\n  ## {family}")
        rows_per_country = []
        for country in COUNTRIES:
            cands = [c for c in pool if c["country_query"] == country and c["family"] == family]
            cands.sort(key=lambda c: c.get("latest_date") or "", reverse=True)
            best = cands[0] if cands else None
            rows_per_country.append((country, best))
        # Sort countries by freshness (best first)
        rows_per_country.sort(
            key=lambda kv: (kv[1].get("latest_date") if kv[1] else ""),
            reverse=True,
        )
        for country, best in rows_per_country:
            if not best:
                print(f"     {country:<12s} — NO HITS")
                continue
            print(f"     {country:<12s} {best['latest_date']:<10s} "
                  f"id={best['id']:<12s} freq={best['freq']:<10s} "
                  f"unit={best['unit'][:18]:<18s} src={best['source'][:14]:<14s} "
                  f"{best['name'][:60]}")

    # ── Report C: coverage summary — how many countries have fresh data per family ──
    print()
    print("=" * 72)
    print("  REPORT C — Coverage summary (does any family work for all 10?)")
    print("=" * 72)
    print(f"\n  {'Family':<22s} | {'Median':<11s} | {'Min':<11s} | {'Max':<11s} | "
          f"{'Through 2026-Q1':<18s} | {'Missing':<8s}")
    print(f"  {'-'*22} | {'-'*11} | {'-'*11} | {'-'*11} | {'-'*18} | {'-'*8}")
    for family, _ in MEASURE_FAMILIES:
        latest_per_country = []
        missing = 0
        for country in COUNTRIES:
            cands = [c for c in pool if c["country_query"] == country and c["family"] == family]
            cands.sort(key=lambda c: c.get("latest_date") or "", reverse=True)
            if cands and cands[0].get("latest_date"):
                latest_per_country.append(cands[0]["latest_date"])
            else:
                missing += 1
        if not latest_per_country:
            print(f"  {family:<22s} | NO DATA")
            continue
        latest_per_country.sort()
        median = latest_per_country[len(latest_per_country) // 2]
        min_d = latest_per_country[0]
        max_d = latest_per_country[-1]
        through_q1 = sum(1 for d in latest_per_country if d >= "2026-01-01")
        print(f"  {family:<22s} | {median:<11s} | {min_d:<11s} | {max_d:<11s} | "
              f"{through_q1:>2d} / {len(COUNTRIES):<2d}            | {missing:<8d}")

    print("\nDone. Use Report C to pick the best family, then Report B for the per-country ids.")


if __name__ == "__main__":
    main()
