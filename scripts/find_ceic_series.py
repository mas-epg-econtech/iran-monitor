#!/usr/bin/env python3
"""
Search CEIC for the MAS Core Inflation MoM series (we currently only have the
YoY: source_key 541733617). Reuses the working search pattern from
scripts/energy/ceic_search.py.

Auto-loads creds from Iran Monitor/.env (with ME Dashboard's .env as fallback).

Run:
  python3.11 scripts/find_ceic_series.py
Or with custom queries:
  python3.11 scripts/find_ceic_series.py "MAS Core" "Singapore CPI"
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


_IRAN_MONITOR_ROOT = Path(__file__).resolve().parent.parent
_load_env(_IRAN_MONITOR_ROOT / ".env")
_load_env(Path("/Users/kevinlim/Documents/MAS/Projects/ESD/Middle East Dashboard/.env"))


def _timeout_handler(signum, frame):
    raise TimeoutError("timed out")


def search_and_print(query: str, geo: str = "", max_results: int = 25) -> None:
    """Search CEIC and print results — pattern lifted from scripts/energy/ceic_search.py."""
    from ceic_api_client.pyceic import Ceic

    print(f"\n{'=' * 70}")
    print(f"  SEARCH: {query!r}  (geo={geo or 'ALL'})")
    print(f"{'=' * 70}")
    sys.stdout.flush()

    old = signal.signal(signal.SIGALRM, _timeout_handler)
    signal.alarm(45)

    try:
        kwargs = {"limit": max_results}
        if geo:
            kwargs["geo"] = [geo]

        result = Ceic.search(query, **kwargs)
        signal.alarm(0)

        search_data = result.data if hasattr(result, "data") else result
        total = getattr(search_data, "total", 0) or 0
        items = getattr(search_data, "items", []) or []

        if total == 0 or not items:
            print(f"  No results (total={total}).")
            return

        print(f"  {total} total matches, showing {len(items)}:\n")
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
            status_obj = getattr(meta, "status", None)
            status = getattr(status_obj, "name", "?") if status_obj else "?"
            source_obj = getattr(meta, "source", None)
            source = getattr(source_obj, "name", "?") if source_obj else "?"
            subscribed = getattr(item, "subscribed", None)
            sub_tag = " [SUBSCRIBED]" if subscribed else ""

            print(f"  ID: {sid}{sub_tag}")
            print(f"    Name: {name}")
            print(f"    Country: {country}  Freq: {freq}  Unit: {unit}  Status: {status}")
            print(f"    Source: {source}\n")

    except TimeoutError:
        signal.alarm(0)
        print("  TIMED OUT (45s).")
    except Exception as exc:
        signal.alarm(0)
        print(f"  ERROR: {exc}")
        import traceback
        traceback.print_exc()
    finally:
        signal.signal(signal.SIGALRM, old)
    sys.stdout.flush()


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
    print("Login OK")

    # Default queries — no geo filter (CEIC's geo codes don't always map to
    # ISO codes; safer to put "Singapore" in the query itself).
    queries = sys.argv[1:] or [
        "MAS Core Inflation",
        "Singapore Core Inflation",
        "Singapore CPI",
    ]
    for q in queries:
        search_and_print(q, max_results=25)

    Ceic.logout()
    print("\nDone. Look for entries with Freq=Monthly and Unit '% Month over Month' (or similar).")


if __name__ == "__main__":
    main()
