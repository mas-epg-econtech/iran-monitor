#!/usr/bin/env python3
"""
Search CEIC for series relevant to dashboard nodes that are still missing data.
"""

import os
import sys
import signal

from ceic_api_client.pyceic import Ceic


def _timeout_handler(signum, frame):
    raise TimeoutError("timed out")


def search_and_print(query: str, geo: str = "", max_results: int = 15):
    """Search CEIC and print results."""
    print(f"\n{'=' * 70}")
    print(f"  SEARCH: \"{query}\"  (geo={geo or 'ALL'})")
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

        search_data = result.data if hasattr(result, 'data') else result
        total = getattr(search_data, 'total', 0) or 0
        items = getattr(search_data, 'items', []) or []

        if total == 0 or not items:
            print(f"  No results (total={total}).")
            return

        print(f"  {total} total matches, showing {len(items)}:\n")

        for item in items:
            meta = getattr(item, 'metadata', None)
            if meta is None:
                continue

            sid = getattr(meta, 'id', '?')
            name = getattr(meta, 'name', '?')

            freq_obj = getattr(meta, 'frequency', None)
            freq = getattr(freq_obj, 'name', '?') if freq_obj else '?'

            unit_obj = getattr(meta, 'unit', None)
            unit = getattr(unit_obj, 'name', '?') if unit_obj else '?'

            country_obj = getattr(meta, 'country', None)
            country = getattr(country_obj, 'name', '?') if country_obj else '?'

            status_obj = getattr(meta, 'status', None)
            status = getattr(status_obj, 'name', '?') if status_obj else '?'

            source_obj = getattr(meta, 'source', None)
            source = getattr(source_obj, 'name', '?') if source_obj else '?'

            subscribed = getattr(item, 'subscribed', None)
            sub_tag = " [SUBSCRIBED]" if subscribed else ""

            print(f"  ID: {sid}{sub_tag}")
            print(f"    Name: {name}")
            print(f"    Country: {country}  Freq: {freq}  Unit: {unit}  Status: {status}")
            print(f"    Source: {source}")
            print()

    except TimeoutError:
        signal.alarm(0)
        print("  TIMED OUT (45s). Skipping.")
    except Exception as exc:
        signal.alarm(0)
        print(f"  ERROR: {exc}")
        import traceback
        traceback.print_exc()
    finally:
        signal.signal(signal.SIGALRM, old)

    sys.stdout.flush()


def main():
    username = os.environ.get("CEIC_USERNAME", "")
    password = os.environ.get("CEIC_PASSWORD", "")
    if not username or not password:
        print("ERROR: Set CEIC_USERNAME and CEIC_PASSWORD.")
        sys.exit(1)

    Ceic.login(username, password)
    print("Logged in.\n")

    # ================================================================
    # PRICES — global/SG commodity and chemical prices
    # ================================================================
    print("=" * 70)
    print("  SECTION A: PRICES (global benchmarks)")
    print("=" * 70)

    # Ethane — Mont Belvieu is the global benchmark
    search_and_print("ethane spot price", max_results=10)
    search_and_print("Mont Belvieu ethane", max_results=10)
    search_and_print("ethane natural gas liquid", max_results=10)

    # Helium — global producer price
    search_and_print("helium price", max_results=10)
    search_and_print("helium production", max_results=10)

    # Fertilisers — urea is the key benchmark
    search_and_print("urea price", max_results=10)
    search_and_print("ammonia price", max_results=10)
    search_and_print("fertilizer commodity price", max_results=10)

    # Derivative Products — plastics, paints, pharma intermediates
    search_and_print("polyethylene price Asia", max_results=10)
    search_and_print("polypropylene price", max_results=10)
    search_and_print("PVC price", max_results=10)
    search_and_print("methanol price", max_results=10)

    # ================================================================
    # ECONOMIC ACTIVITY — Singapore-specific sector indicators
    # ================================================================
    print("\n" + "=" * 70)
    print("  SECTION B: ECONOMIC ACTIVITY (Singapore)")
    print("=" * 70)

    # Real Estate — property transactions, price index, permits
    search_and_print("Singapore property price", max_results=10)
    search_and_print("Singapore real estate transaction", max_results=10)
    search_and_print("Singapore housing price index", max_results=10)

    # Water & Waste — utilities output, water production, waste
    search_and_print("Singapore water production", max_results=10)
    search_and_print("Singapore utilities output", max_results=10)
    search_and_print("Singapore waste", max_results=10)
    search_and_print("Singapore electricity water gas", max_results=10)

    Ceic.logout()
    print("\nDone. Review the series IDs above and add useful ones to src/series_config.py")


if __name__ == "__main__":
    main()
