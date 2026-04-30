#!/usr/bin/env python3
"""
SingStat Table Builder discovery probe — find the right tables for monthly
chemical exports by partner (SITC 5xx series).

Goal: identify which M45xxxx table(s) expose:
  - Singapore's domestic exports / re-exports of chemicals (SITC 5xx)
  - Broken down by destination country (partner)
  - Monthly frequency
  - Going back at least to 2023 (preferably earlier)

The existing ingestor uses M451001 (petroleum, SITC 33). Other M45xxxx
tables in the trade family expose different cuts; this probe lists each
table's title, frequency, time range, and indicator-tree shape so we can
pick the right ones.

What it does:
  For each candidate table_id, calls the public Table Builder metadata
  endpoint and prints:
    - title
    - frequency (monthly / quarterly / annual)
    - row count + date range
    - the top-level branches of the indicator tree (so we can see whether
      the table has a partner dimension and a SITC dimension)

Run from Iran Monitor root:
  python3.11 scripts/probe_singstat_chemicals.py
  python3.11 scripts/probe_singstat_chemicals.py M451001 M451021 M451031

Add table IDs as args to override the default candidate list.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import requests


# Candidate trade tables. The exact IDs depend on SingStat's catalog at the
# time of writing — we'll fetch each and report what's there. If a table
# returns 404, we just skip it.
CANDIDATE_TABLES = [
    "M451001",   # what we already use — Total Merchandise Trade by Commodity Section
    "M451011",
    "M451021",
    "M451031",
    "M451041",
    "M451051",
    "M451061",
    "M451071",
    "M451081",
    "M451091",
    # Country-specific trade tables (alternative naming)
    "M451591",
    "M451601",
    "M451611",
    "M451621",
]


SINGSTAT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
}

META_URL = (
    "https://tablebuilder.singstat.gov.sg/api/doswebcontent/1/"
    "StatisticTableFileUpload/StatisticTable/{table_id}"
)

ROW_URL = (
    "https://tablebuilder.singstat.gov.sg/rowdata/{guid}_{table_id}_{series_no}.json"
)


def probe_table_metadata(table_id: str) -> dict | None:
    """Fetch metadata for a SingStat table. Returns the inner Data dict on
    success, or None on miss. Uses the correct field names this time."""
    try:
        resp = requests.get(META_URL.format(table_id=table_id), headers=SINGSTAT_HEADERS, timeout=30)
    except Exception as exc:
        print(f"  REQUEST FAIL: {exc}")
        return None
    if resp.status_code != 200:
        print(f"  HTTP {resp.status_code}: {resp.text[:160]}")
        return None
    try:
        payload = resp.json()
    except Exception as exc:
        print(f"  JSON PARSE FAIL: {exc}")
        return None
    return payload.get("Data") or None


def print_table_metadata(table_id: str, data: dict) -> None:
    """Pretty-print the SingStat table metadata using the correct field keys."""
    print(f"\n{'='*78}")
    print(f"  TABLE: {table_id}")
    print(f"{'='*78}")
    print(f"  Title:           {data.get('matrixTitle', '?')}")
    print(f"  Group:           {data.get('groupTitle', '?')}")
    print(f"  Unit:            {data.get('unitMeasurement', '?')}")
    print(f"  Frequency:       {data.get('frequencyType', '?')}")
    print(f"  Period range:    {data.get('startPeriod', '?')}  →  {data.get('endPeriod', '?')}")
    print(f"  Last updated:    {data.get('effectiveDate', '?')}")
    print(f"  Source:          {data.get('dataSource', '?')}")
    # Note: `sameGroup` is a bool flag in this API (not a sibling-table list)
    sg_flag = data.get("sameGroup")
    if sg_flag is not None:
        print(f"  sameGroup flag:  {sg_flag}")


def probe_seriesno(table_id: str, guid: str, series_no: str) -> dict | None:
    """Fetch one seriesNo's row data from a SingStat table. Returns the
    list on success (or None). Useful for discovering the indicator-tree
    shape since the metadata endpoint doesn't include it."""
    url = ROW_URL.format(guid=guid, table_id=table_id, series_no=series_no)
    try:
        resp = requests.get(url, headers=SINGSTAT_HEADERS, timeout=30)
    except Exception:
        return None
    if resp.status_code != 200:
        return None
    try:
        return resp.json()
    except Exception:
        return None


def discover_seriesno_tree(table_id: str, guid: str, max_depth: int = 4) -> None:
    """Walk seriesNo "1", "2", "3", ... at each level to discover what's
    addressable in the table. Prints which paths return data.

    Trade tables typically have:
      seriesNo "1" / "2" / "3" / "4" / "5" — flows (Total Trade / Imports /
        Total Exports / Domestic Exports / Re-Exports)
      seriesNo "2.1" / "2.2" / "2.3" — within Imports, top SITC chapters
      seriesNo "2.1.1" — drilldown
      ...
    """
    print(f"\n  --- seriesNo tree probe for {table_id} ---")
    # Root — try seriesNo "1" through "10"
    for top in range(1, 11):
        top_str = str(top)
        rows = probe_seriesno(table_id, guid, top_str)
        if rows is None or not isinstance(rows, list) or not rows:
            continue
        sample = rows[0]
        sample_key = sample.get("Key", "?") if isinstance(sample, dict) else "?"
        sample_val = sample.get("Value", "?") if isinstance(sample, dict) else "?"
        print(f"    seriesNo={top_str:<8s}  {len(rows):>4d} pts  e.g. ({sample_key} = {sample_val})")
        if max_depth >= 2:
            for sub in range(1, 12):
                sub_no = f"{top}.{sub}"
                rows2 = probe_seriesno(table_id, guid, sub_no)
                if rows2 and isinstance(rows2, list) and len(rows2) > 0:
                    s2 = rows2[0]
                    s2_key = s2.get("Key", "?") if isinstance(s2, dict) else "?"
                    s2_val = s2.get("Value", "?") if isinstance(s2, dict) else "?"
                    print(f"        seriesNo={sub_no:<10s}  {len(rows2):>4d} pts  e.g. ({s2_key} = {s2_val})")
                    # Drill one more level — this is where SITC sub-codes
                    # like 5.1 / 5.4 will surface for M451041.
                    if max_depth >= 3:
                        for sub2 in range(1, 12):
                            sub2_no = f"{top}.{sub}.{sub2}"
                            rows3 = probe_seriesno(table_id, guid, sub2_no)
                            if rows3 and isinstance(rows3, list) and len(rows3) > 0:
                                s3 = rows3[0]
                                s3_key = s3.get("Key", "?") if isinstance(s3, dict) else "?"
                                s3_val = s3.get("Value", "?") if isinstance(s3, dict) else "?"
                                print(f"            seriesNo={sub2_no:<12s}  {len(rows3):>4d} pts  e.g. ({s3_key} = {s3_val})")


def main():
    args = sys.argv[1:]
    # First pass: list all 9 working tables with their proper titles, so we
    # can see at a glance which one is "by partner / SITC / monthly".
    print(f"{'='*78}")
    print(f"  PASS 1: Table catalog with proper titles")
    print(f"{'='*78}")
    table_data: dict[str, dict] = {}
    for table_id in (args if args else CANDIDATE_TABLES):
        data = probe_table_metadata(table_id)
        if data:
            table_data[table_id] = data
            print(f"\n  {table_id}")
            print(f"    Title:     {data.get('matrixTitle', '?')}")
            print(f"    Group:     {data.get('groupTitle', '?')}")
            print(f"    Frequency: {data.get('frequencyType', '?')}")
            print(f"    Period:    {data.get('startPeriod', '?')} → {data.get('endPeriod', '?')}")

    # Second pass: full metadata + sibling-table list for tables that exist.
    # The "sameGroup" field is gold — it lists every other table in the same
    # SingStat publication group, which tells us what other cuts are available.
    print(f"\n\n{'='*78}")
    print(f"  PASS 2: Full metadata + sibling tables in the same publication group")
    print(f"{'='*78}")
    for table_id, data in table_data.items():
        print_table_metadata(table_id, data)

    # Third pass: probe seriesNo tree for M451041 — the critical table for
    # this work (Domestic Exports × 2-digit SITC, where SITC 5 / 51 / 54
    # live). Skipping M451001 since we already know its structure from the
    # existing petroleum ingestor.
    tid = "M451041"
    if table_data.get(tid):
        d = table_data[tid]
        guid = d.get("id") or d.get("titleId")
        if guid:
            print(f"\n{'='*78}")
            print(f"  PASS 3: seriesNo tree of {tid}")
            print(f"{'='*78}")
            discover_seriesno_tree(tid, guid, max_depth=3)


if __name__ == "__main__":
    main()
