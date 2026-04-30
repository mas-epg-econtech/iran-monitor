#!/usr/bin/env python3
"""
CEIC discovery probe — find historical price/yield series to backfill the
day-by-day-only series on the Regional Financial Markets tab.

What we need:
  Commodities (currently scraped from investing.com, ~30 days history):
    - LME Nickel
    - SHFE Nickel  (we dropped this from the dash; revisit if CEIC has it)
    - Newcastle Coal (thermal coal benchmark)
    - JKM LNG (Japan/Korea Marker spot LNG)
    - Crude Palm Oil (Bursa Malaysia FCPO)
    - Rubber TSR20

  Bond yields (currently from ADB AsianBondsOnline, ~30 days):
    - Indonesia 10Y
    - Malaysia 10Y
    - Philippines 10Y
    - Thailand 10Y
    - Vietnam 10Y

For each query, prints the top hits with their CEIC source key, frequency,
unit, and subscription status. Manual inspection then identifies the right
series ID(s) to wire into series_config.py.

Run:
  python3.11 scripts/probe_ceic_markets.py
"""
from __future__ import annotations

import os
import signal
import sys
from pathlib import Path


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


# Search query buckets — each query is run independently and results listed.
QUERIES = {
    # ── Commodities ────────────────────────────────────────────────────
    "Commodities — Nickel": [
        "LME Nickel price",
        "London Metal Exchange Nickel",
        "Nickel cash settlement",
        "SHFE Nickel",
        "Shanghai Nickel futures",
    ],
    "Commodities — Coal": [
        "Newcastle Coal price",
        "Thermal coal Newcastle",
        "Australia coal export price",
        "Coal benchmark FOB",
    ],
    "Commodities — LNG": [
        "JKM LNG",
        "Japan Korea Marker LNG",
        "Asia LNG spot price",
        "Platts JKM",
    ],
    "Commodities — Palm oil": [
        "Crude Palm Oil price",
        "Bursa Malaysia FCPO",
        "Malaysia palm oil price",
        "Crude palm oil futures",
    ],
    "Commodities — Rubber": [
        "Rubber TSR20",
        "Natural rubber price",
        "SGX Rubber futures",
        "Singapore rubber",
    ],
    # ── Bond yields ────────────────────────────────────────────────────
    "Bonds — Indonesia 10Y": [
        "Indonesia 10 year government bond yield",
        "Indonesia government bond 10Y",
        "Indonesia sovereign yield",
    ],
    "Bonds — Malaysia 10Y": [
        "Malaysia 10 year government bond yield",
        "Malaysia government securities 10Y",
    ],
    "Bonds — Philippines 10Y": [
        "Philippines 10 year government bond yield",
        "Philippines treasury bond 10Y",
    ],
    "Bonds — Thailand 10Y": [
        "Thailand 10 year government bond yield",
        "Thailand sovereign yield 10Y",
    ],
    "Bonds — Vietnam 10Y": [
        "Vietnam 10 year government bond yield",
        "Vietnam government bond 10Y",
    ],
}

MAX_RESULTS_PER_QUERY = 8
TIMEOUT_SEC = 45


def _timeout_handler(signum, frame):
    raise TimeoutError("timed out")


def search_one(query: str, max_results: int = MAX_RESULTS_PER_QUERY):
    from ceic_api_client.pyceic import Ceic

    old = signal.signal(signal.SIGALRM, _timeout_handler)
    signal.alarm(TIMEOUT_SEC)
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
            try:
                first = str(getattr(meta, "first_obs_date", "") or "")
                last  = str(getattr(meta, "last_update_time", "") or "")
            except Exception:
                first, last = "", ""
            out.append((sid, name, country, freq, unit, source, subscribed, first, last))
    except TimeoutError:
        signal.alarm(0)
        print(f"  TIMEOUT after {TIMEOUT_SEC}s")
    except Exception as exc:
        signal.alarm(0)
        print(f"  ERROR: {exc}")
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

    summary: dict[str, int] = {}

    for bucket_name, queries in QUERIES.items():
        print(f"\n{'=' * 78}")
        print(f"  BUCKET: {bucket_name}")
        print(f"{'=' * 78}")

        bucket_hits = []
        seen_ids = set()
        for q in queries:
            hits = search_one(q)
            print(f"  [{len(hits)} hits] {q!r}")
            for h in hits:
                sid = h[0]
                if sid in seen_ids:
                    continue
                seen_ids.add(sid)
                bucket_hits.append(h)

        # Filter heuristic: prefer subscribed series with daily/weekly/monthly
        # frequency (not yearly aggregates).
        good = [h for h in bucket_hits
                if h[6] and h[3].lower() in ("daily", "weekly", "monthly")]
        print(f"\n  Filtered candidates ({len(good)} unique, subscribed + non-yearly):")
        if not good:
            print("    [none]")
        else:
            for sid, name, country, freq, unit, source, sub, first, last in good[:8]:
                print(f"    {sid}  {name[:80]}")
                print(f"       country={country}  freq={freq}  unit={unit}  src={source}")
                if last:
                    print(f"       last_update={last[:25]}")
        summary[bucket_name] = len(good)

    # Cross-bucket summary
    print(f"\n{'=' * 78}")
    print("  SUMMARY — candidates per bucket")
    print(f"{'=' * 78}")
    for b, n in summary.items():
        print(f"  {b:40s}  {n:>3} candidate(s)")

    Ceic.logout()
    print("\nDone.")


if __name__ == "__main__":
    main()
