#!/usr/bin/env python3
"""
Diagnostic probe — figure out why our SG-share ratios are blowing up.

Hypothesis: when we query Comtrade with partnerCode=0 ("World"), the API may
return per-partner detail rows for some reporters rather than a single
World-aggregate row. Our previous probe took data[0] blindly, so for those
reporters the "World value" was actually an arbitrary single partner — making
the denominator tiny and the SG-share ratio explode (>100%, sometimes by
orders of magnitude).

What this does:
  For ONE reporter (configurable; defaults to India), ONE year (2024):
    - Query with partnerCode=0 (intended: World aggregate)
    - Dump row count
    - Show the first 10 rows' partnerCode + partnerDesc + primaryValue
    - Sum primaryValue across all rows (in case the answer is sum-of-rows)
    - Compare with a separate query for partnerCode=702 (Singapore)

The goal: identify the *correct* way to query for the World total. Likely
options once we see the data:
  1. partnerCode=0 returns a single row with partnerDesc='World' — use it
  2. partnerCode=0 returns many rows — sum primaryValue across them
  3. partnerCode=0 returns nothing / error — try a different aggregation
     code or omit partnerCode and aggregate ourselves

Run from Iran Monitor root:
  python3.11 scripts/probe_comtrade_world_aggregation.py
  python3.11 scripts/probe_comtrade_world_aggregation.py 360 2024  # Indonesia, 2024
"""
from __future__ import annotations

import json
import os
import sys
import time
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


COMTRADE_URL = "https://comtradeapi.un.org/data/v1/get/C/A/S4"
SITC_CODE = "5"


def fetch(reporter_code: str, partner_code: str, year: str, headers: dict,
          extra_params: dict | None = None) -> dict:
    """One call. Returns {status, n_rows, raw_payload}.

    `extra_params` allows adding e.g. motCode=0, customsCode=C00 to collapse
    the response to a single aggregate row per partner.
    """
    import requests
    params = {
        "reporterCode": reporter_code,
        "partnerCode":  partner_code,
        "period":       year,
        "cmdCode":      SITC_CODE,
        "flowCode":     "M",
        "includeDesc":  "true",
    }
    if extra_params:
        params.update(extra_params)
    qs = "&".join(f"{k}={v}" for k, v in params.items() if k not in ("includeDesc",))
    print(f"  GET {COMTRADE_URL}?{qs}")
    delay = 2.0
    for attempt in range(5):
        try:
            resp = requests.get(COMTRADE_URL, params=params, headers=headers, timeout=30)
        except Exception:
            time.sleep(delay)
            delay *= 2
            continue
        if resp.status_code == 200:
            try:
                return {"status": 200, "payload": resp.json()}
            except Exception:
                return {"status": 200, "payload": None}
        if resp.status_code in (429, 500, 502, 503, 504):
            ra = resp.headers.get("Retry-After")
            wait = float(ra) if ra and ra.isdigit() else delay
            print(f"     {resp.status_code} retry-after={wait}s")
            time.sleep(wait)
            delay *= 2
            continue
        return {"status": resp.status_code, "payload": None, "text": resp.text[:200]}
    return {"status": 429, "payload": None}


def diag_print(label: str, result: dict) -> None:
    """Print row count, sums, and breakdown by aggregation/customs flags."""
    print(f"\n  --- {label} ---")
    if result.get("status") != 200 or not result.get("payload"):
        print(f"    HTTP {result.get('status')}  text={result.get('text', '')!r}")
        return
    payload = result["payload"]
    rows = payload.get("data") or []
    print(f"    rows returned: {len(rows)}")
    if not rows:
        print("    (empty)")
        return

    # Total across all rows (for completeness)
    total = sum(r.get("primaryValue") or 0 for r in rows
                if isinstance(r.get("primaryValue"), (int, float)))
    print(f"    sum(primaryValue) all rows: {total:>20,.0f}")

    # Sample one row's full keys for debugging
    print(f"    sample row keys: {sorted(rows[0].keys())}")

    # Breakdown by aggregation flags (do leaf rows + parent aggregate rows
    # both exist? If so we'd be double-counting by summing.)
    from collections import Counter
    agg_counter = Counter()
    leaf_counter = Counter()
    aggrlvl_counter = Counter()
    for r in rows:
        agg_counter[r.get("isAggregate")] += 1
        leaf_counter[r.get("isLeaf")] += 1
        aggrlvl_counter[r.get("aggrLevel")] += 1
    print(f"    isAggregate distribution: {dict(agg_counter)}")
    print(f"    isLeaf distribution:      {dict(leaf_counter)}")
    print(f"    aggrLevel distribution:   {dict(aggrlvl_counter)}")

    # Breakdown by motCode + customsCode — the dimensions splitting our rows
    mot_counter = Counter(r.get("motCode") for r in rows)
    customs_counter = Counter(r.get("customsCode") for r in rows)
    print(f"    motCode distribution:     {dict(sorted(mot_counter.items(), key=lambda kv: -kv[1])[:10])}")
    print(f"    customsCode distribution: {dict(sorted(customs_counter.items(), key=lambda kv: -kv[1])[:10])}")

    # Sums under three filtering strategies — to confirm which is right
    sum_all = total
    sum_agg = sum(r.get("primaryValue") or 0 for r in rows
                  if r.get("isAggregate") and isinstance(r.get("primaryValue"), (int, float)))
    sum_leaf = sum(r.get("primaryValue") or 0 for r in rows
                   if r.get("isLeaf") and isinstance(r.get("primaryValue"), (int, float)))
    print(f"    sum strategies:")
    print(f"      sum_all      = {sum_all:>20,.0f}  (every row)")
    print(f"      sum_aggregate= {sum_agg:>20,.0f}  (rows where isAggregate=true)")
    print(f"      sum_leaf     = {sum_leaf:>20,.0f}  (rows where isLeaf=true)")


def main():
    args = sys.argv[1:]
    reporter_code = args[0] if len(args) > 0 else "699"   # default: India
    year = args[1] if len(args) > 1 else "2024"

    api_key = os.environ.get("COMTRADE_API_KEY", "")
    if not api_key:
        sys.exit("COMTRADE_API_KEY not set in .env.")
    headers = {"Ocp-Apim-Subscription-Key": api_key, "Accept": "application/json"}

    print(f"\n=== Diagnostic probe: reporter={reporter_code}  year={year}  SITC={SITC_CODE} ===")

    print(f"\n[Query 1] partnerCode=0 (intended: World aggregate)")
    r_world = fetch(reporter_code, "0", year, headers)
    diag_print("partnerCode=0", r_world)

    time.sleep(2.0)

    print(f"\n[Query 2] partnerCode=702 (Singapore)")
    r_sg = fetch(reporter_code, "702", year, headers)
    diag_print("partnerCode=702", r_sg)

    time.sleep(2.0)

    print(f"\n[Query 3] partnerCode=156 (China — sanity check, large bilateral)")
    r_cn = fetch(reporter_code, "156", year, headers)
    diag_print("partnerCode=156", r_cn)

    time.sleep(2.0)

    # ── Query 4: try to collapse the rows via motCode=0 + customsCode=C00 ──
    print(f"\n[Query 4] partnerCode=0 with motCode=0 + customsCode=C00 (try to collapse rows)")
    r_collapsed = fetch(reporter_code, "0", year, headers,
                        extra_params={"motCode": "0", "customsCode": "C00"})
    diag_print("partnerCode=0 + motCode=0 + customsCode=C00", r_collapsed)

    # ── Final summary ────────────────────────────────────────────────────
    print()
    print("=" * 78)
    print("  Suggested aggregation strategy")
    print("=" * 78)

    def _sum(r):
        if r.get("status") != 200 or not r.get("payload"):
            return None
        return sum(x.get("primaryValue") or 0 for x in r["payload"].get("data", [])
                   if isinstance(x.get("primaryValue"), (int, float)))

    w_all = _sum(r_world)
    s_all = _sum(r_sg)
    c_all = _sum(r_cn)
    w_col = _sum(r_collapsed)

    if w_all and s_all:
        print(f"  Sum-all-rows ratios:")
        print(f"    SG share of {reporter_code}'s chemicals:   {s_all/w_all*100:6.2f}%")
        if c_all:
            print(f"    CN share of {reporter_code}'s chemicals:   {c_all/w_all*100:6.2f}%")
            print(f"    SG + CN combined:                        {(s_all+c_all)/w_all*100:6.2f}%")
        print(f"    World total (all rows summed):    {w_all:>20,.0f}")
    if w_col:
        print(f"  Collapsed (motCode=0+customsCode=C00) World total: {w_col:>20,.0f}")
        if w_all and abs(w_col - w_all) / max(w_all, 1) < 0.01:
            print("    → matches sum-all-rows within 1%. Use the collapse params for clean ingest.")
        else:
            print("    → differs from sum-all-rows. Check which is correct before scaling.")


if __name__ == "__main__":
    main()
