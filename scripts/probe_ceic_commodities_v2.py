#!/usr/bin/env python3
"""
CEIC discovery probe v2 — broader keyword search for the 3 commodity
benchmarks where the first probe (probe_ceic_markets.py) returned 0 hits
or only weak proxies:
  - Newcastle Coal (thermal coal, Asian seaborne benchmark)
  - Crude Palm Oil (Bursa Malaysia FCPO benchmark)
  - Rubber TSR20 (SGX benchmark, dominant Thai/Indonesian/Vietnamese supply)

Run on your Mac (proprietary CEIC client):
  cd "/Users/kevinlim/Documents/MAS/Projects/ESD/Iran Monitor"
  python3.11 -u scripts/probe_ceic_commodities_v2.py 2>&1 | tee /tmp/ceic_v2.log
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


# Broader queries — drop product-specific naming, look for benchmark prices
# in ASEAN countries (Malaysia for palm oil, Thailand/Indonesia for rubber,
# Australia for coal, etc.) and for "spot" / "FOB" / "ICE" / "futures" terms.
QUERIES = {
    "Newcastle Coal / Thermal Coal": [
        "Australia thermal coal export price",
        "Coal: Australia: FOB",
        "Coal: Newcastle",
        "ICE coal futures",
        "Coal: Asia",
        "Coal: Spot Price",
        "Australia coal price benchmark",
        "Energy: Coal: Price",
    ],
    "Palm oil benchmark (FCPO MYR or USD)": [
        "Bursa Malaysia palm oil",
        "Palm oil: Bursa",
        "FCPO Malaysia",
        "Crude palm oil: third position",
        "Crude palm oil: settlement price",
        "Malaysia: MPOB Price",
        "Palm oil: Settlement",
        "Crude Palm Oil: Spot: Malaysia",
        "Palm Olein futures",
    ],
    "Rubber TSR20 / Asia rubber": [
        "Rubber: Singapore: SGX",
        "TSR20 SGX",
        "Standard Indonesian Rubber",
        "Singapore rubber TSR",
        "Rubber: Bangkok",
        "Rubber: Settlement Price",
        "Rubber: Closing Price",
        "Natural Rubber: TSR20",
        "Thailand rubber price",
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
                last = str(getattr(meta, "last_update_time", "") or "")
            except Exception:
                last = ""
            out.append((sid, name, country, freq, unit, source, subscribed, last))
    except TimeoutError:
        signal.alarm(0)
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
        sys.exit("ceic_api_client not installed.")
    username = os.environ.get("CEIC_USERNAME", "")
    password = os.environ.get("CEIC_PASSWORD", "")
    if not username or not password:
        sys.exit("Set CEIC_USERNAME and CEIC_PASSWORD.")
    Ceic.login(username, password)
    print("Login OK\n")

    for bucket, queries in QUERIES.items():
        print(f"\n{'=' * 78}")
        print(f"  BUCKET: {bucket}")
        print(f"{'=' * 78}")
        seen = set()
        all_hits = []
        for q in queries:
            hits = search_one(q)
            print(f"  [{len(hits)} hits] {q!r}")
            for h in hits:
                if h[0] in seen:
                    continue
                seen.add(h[0])
                all_hits.append(h)
        # Filter: subscribed + Daily/Weekly/Monthly (skip yearly)
        good = [h for h in all_hits
                if h[6] and h[3].lower() in ("daily", "weekly", "monthly")]
        print(f"\n  Filtered candidates ({len(good)} unique, subscribed + non-yearly):")
        if not good:
            print("    [none]")
        else:
            for sid, name, country, freq, unit, source, sub, last in good[:10]:
                print(f"    {sid}  {name[:80]}")
                print(f"       country={country}  freq={freq}  unit={unit}  src={source}")
                if last:
                    print(f"       last_update={last[:25]}")

    Ceic.logout()
    print("\nDone.")


if __name__ == "__main__":
    main()
