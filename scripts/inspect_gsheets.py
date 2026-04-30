#!/usr/bin/env python3
"""
Inspect a Google Sheet via the same service-account auth used by the
ingestion pipeline (scripts/energy/update_data.py:fetch_google_sheets_series).

Two modes:

  1. Default — full structural inspection: lists every tab with its dimensions
     and dumps the first N rows of each tab so we can see headers + sample
     data in one shot. Use this to confirm a sheet's layout before wiring it
     into the ingestion pipeline.

  2. --tab TAB_NAME — dump the entire tab (or up to --max-rows rows) so we
     can inspect the full series catalogue / data structure.

Sheet ID source order:
  - --sheet-id command-line argument (overrides everything)
  - GOOGLE_SHEETS_INSPECT_ID env var
  - GOOGLE_SHEETS_SPREADSHEET_ID env var (the production sheet)

Run:
  python3.11 scripts/inspect_gsheets.py
  python3.11 scripts/inspect_gsheets.py --sheet-id 1AWC6ZWTXzL...
  python3.11 scripts/inspect_gsheets.py --tab Daily --max-rows 20
"""
from __future__ import annotations

import argparse
import json
import os
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


# ── Auth — copied verbatim from scripts/energy/update_data.py ────────────
def _get_sheets_service():
    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build

    sa_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")
    sa_file = os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE", "")

    if sa_json:
        info = json.loads(sa_json)
    elif sa_file and Path(sa_file).exists():
        info = json.loads(Path(sa_file).read_text())
    else:
        sys.exit(
            "ERROR: Set GOOGLE_SERVICE_ACCOUNT_JSON (raw JSON) or "
            "GOOGLE_SERVICE_ACCOUNT_FILE (path) in .env"
        )

    creds = Credentials.from_service_account_info(
        info, scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"]
    )
    return build("sheets", "v4", credentials=creds, cache_discovery=False), info


def _truncate(s: str, n: int = 30) -> str:
    s = str(s) if s is not None else ""
    return s if len(s) <= n else s[: n - 1] + "…"


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect a Google Sheet's structure.")
    parser.add_argument("--sheet-id", default=None, help="Spreadsheet ID (overrides env vars).")
    parser.add_argument("--tab", default=None, help="If set, dump only this tab in full.")
    parser.add_argument("--max-rows", type=int, default=8, help="Max rows to dump per tab in default mode (default 8).")
    parser.add_argument("--max-cols", type=int, default=10, help="Max columns to display per row (default 10).")
    parser.add_argument("--cell-width", type=int, default=22, help="Truncate each cell to this many chars (default 22).")
    args = parser.parse_args()

    sheet_id = (
        args.sheet_id
        or os.environ.get("GOOGLE_SHEETS_INSPECT_ID")
        or os.environ.get("GOOGLE_SHEETS_SPREADSHEET_ID", "")
    )
    if not sheet_id:
        sys.exit(
            "ERROR: No spreadsheet id. Pass --sheet-id, or set "
            "GOOGLE_SHEETS_INSPECT_ID / GOOGLE_SHEETS_SPREADSHEET_ID in .env."
        )

    service, sa_info = _get_sheets_service()
    print(f"Service account: {sa_info.get('client_email', '?')}")
    print(f"Sheet ID:        {sheet_id}\n")

    # 1. Spreadsheet metadata — title, tabs, dimensions
    try:
        meta = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
    except Exception as exc:
        print(f"FAIL fetching metadata: {exc}\n")
        print("Common causes:")
        print(f"  - Sheet not shared with {sa_info.get('client_email','?')} as Viewer.")
        print(f"  - Wrong sheet id.")
        print(f"  - Sheets API not enabled in the GCP project.")
        sys.exit(1)

    title = meta.get("properties", {}).get("title", "?")
    sheets = meta.get("sheets", [])
    print(f"Title: {title}")
    print(f"Tabs:  {len(sheets)}\n")
    print(f"  {'Tab name':<40s} {'Rows':>6s} {'Cols':>6s}")
    print(f"  {'-'*40} {'-'*6} {'-'*6}")
    for s in sheets:
        p = s["properties"]
        g = p.get("gridProperties", {})
        print(f"  {p['title']:<40s} {g.get('rowCount',0):>6d} {g.get('columnCount',0):>6d}")
    print()

    # 2a. Full-tab mode
    if args.tab:
        target = args.tab
        if not any(s["properties"]["title"] == target for s in sheets):
            sys.exit(f"ERROR: tab {target!r} not found. Available: {[s['properties']['title'] for s in sheets]}")
        print(f"=== Full content of tab '{target}' (capped at {args.max_rows} rows) ===")
        result = service.spreadsheets().values().get(
            spreadsheetId=sheet_id, range=target
        ).execute()
        rows = result.get("values", [])
        for i, row in enumerate(rows[: args.max_rows]):
            cells = [_truncate(c, args.cell_width) for c in row[: args.max_cols]]
            print(f"  [{i:>4d}] {cells}")
        if len(rows) > args.max_rows:
            print(f"  ... ({len(rows) - args.max_rows} more rows omitted; raise --max-rows to see)")
        print(f"\n  Total rows in tab: {len(rows)}")
        return

    # 2b. Default mode — first N rows of every tab
    print(f"=== First {args.max_rows} rows of each tab "
          f"(first {args.max_cols} cols, cells truncated to {args.cell_width} chars) ===")
    for s in sheets:
        tab = s["properties"]["title"]
        try:
            result = service.spreadsheets().values().get(
                spreadsheetId=sheet_id,
                range=f"{tab}!A1:{chr(ord('A')+args.max_cols-1)}{args.max_rows}",
            ).execute()
            rows = result.get("values", [])
        except Exception as exc:
            print(f"\n## {tab} — FAIL: {exc}")
            continue
        print(f"\n## {tab}  ({len(rows)} rows shown)")
        for i, row in enumerate(rows):
            cells = [_truncate(c, args.cell_width) for c in row]
            print(f"  [{i}] {cells}")


if __name__ == "__main__":
    main()
