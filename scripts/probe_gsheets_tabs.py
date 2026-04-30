#!/usr/bin/env python3
"""
Discovery probe — list all tabs in the dashboard Google Sheet, and for
any tab not already known to the ingestor, peek at the first 3 rows so
we can plan how to parse it.

Currently the ingestor knows these tabs:
  Price tabs (parsed by `_parse_sheet_tab`):
    - "Refined Product Prices"
    - "Industrial Input Prices"
  Trade tabs (parsed by `_parse_singstat_*_tab`):
    - SHEET_TRADE_IMPORT_ANNUAL  (SG_Annual_Imports)
    - SHEET_TRADE_IMPORT_MONTHLY (SG_Monthly_Imports)
    - SHEET_TRADE_CHEMICALS_DX   (SG_Chemicals_DX)

Anything else is new and needs a parser. Specifically looking for:
  - SG exports of SITC 3 / 333 / 334 / 343 to regional countries
    (parallel to SG_Chemicals_DX but for mineral fuels)
  - SG financial market indicators
"""
from __future__ import annotations

import os
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


# Tabs the ingestor already handles — anything outside this set is "new"
KNOWN_TABS = {
    "Refined Product Prices",
    "Industrial Input Prices",
    "SG_Annual_Imports",
    "SG_Monthly_Imports",
    "SG_Chemicals_DX",
}


def main() -> None:
    spreadsheet_id = os.environ.get("GOOGLE_SHEETS_SPREADSHEET_ID", "")
    cred_file = os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE", "")
    if not spreadsheet_id or not cred_file or not Path(cred_file).exists():
        sys.exit("Missing GOOGLE_SHEETS_SPREADSHEET_ID or GOOGLE_SERVICE_ACCOUNT_FILE.")

    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    creds = service_account.Credentials.from_service_account_file(
        cred_file,
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
    )
    service = build("sheets", "v4", credentials=creds, cache_discovery=False)

    # Fetch sheet metadata — gives us all tab names
    meta = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    tabs = [s["properties"]["title"] for s in meta.get("sheets", [])]

    print(f"Spreadsheet: {meta.get('properties', {}).get('title', '?')!r}")
    print(f"Total tabs: {len(tabs)}\n")

    print("=" * 78)
    print("  ALL TABS")
    print("=" * 78)
    for t in tabs:
        marker = "  KNOWN  " if t in KNOWN_TABS else "  NEW    "
        print(f"  {marker}{t!r}")

    new_tabs = [t for t in tabs if t not in KNOWN_TABS]
    if not new_tabs:
        print("\nNo new tabs found.")
        return

    # Peek at first 15 rows × 12 cols of each new tab — no truncation
    # so titles are visible in full.
    print(f"\n{'=' * 78}")
    print(f"  PEEK at {len(new_tabs)} new tab(s) — first 15 rows × 12 cols (untruncated)")
    print(f"{'=' * 78}")
    for tab in new_tabs:
        print(f"\n--- TAB: {tab!r} ---")
        try:
            result = (
                service.spreadsheets()
                .values()
                .get(spreadsheetId=spreadsheet_id, range=f"{tab}!A1:L15")
                .execute()
            )
            rows = result.get("values", [])
            for i, row in enumerate(rows):
                print(f"  row {i:2d}: {row}")
        except Exception as e:
            print(f"  ERROR reading {tab}: {e}")


if __name__ == "__main__":
    main()
