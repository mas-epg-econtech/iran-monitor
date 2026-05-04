"""
Data pipeline: fetches from CEIC, Google Sheets, UN Comtrade, SingStat, and
Motorist.sg, then writes everything into the SQLite database, builds the
dashboard, computes summary statistics, generates AI narratives, and
rebuilds the dashboard with the fresh narratives embedded.

Run this from your MAS network (where CEIC is accessible).

Usage:
    1. Fill in .env with credentials (see .env.example)
    2. pip3.11 install -r requirements-pipeline.txt
    3. python3.11 scripts/energy/update_data.py
       python3.11 scripts/energy/update_data.py --skip-narratives  # dev iteration
                                                                    # (saves $0.30-1.00
                                                                    #  in API calls)

    NOTE: Must be invoked with python3.11. The subprocess steps (7-10) inherit
    the same interpreter via sys.executable, so launching with python3.11
    propagates through the whole pipeline automatically.

Sources:
    - CEIC API        -> macro indicators (crude oil, transport, financial)
    - Google Sheets   -> Bloomberg terminal data (commodity spot prices)
    - UN Comtrade API -> monthly partner-level trade (crude, products, petchem)
    - SingStat API    -> monthly petroleum import/export totals (M451001)
    - Motorist.sg     -> daily retail fuel prices by brand

Pipeline (12 steps):
    [1/12] CEIC                          [7/12]  PortWatch download (incremental)
    [2/12] Google Sheets                 [8/12]  Shipping nowcast (gated; STL+Ridge)
    [3/12] SingStat trade                [9/12]  Build dashboard (1st pass)
    [4/12] Comtrade regional dep         [10/12] Compute summary stats
    [5/12] SingStat Table Builder        [10b/12] Evaluate narrative triggers
    [6/12] Motorist fuel prices          [11/12] Generate AI narratives (gated)
                                         [12/12] Rebuild dashboard with narratives

Shipping pipeline gate:
    Step 8 (nowcast compute) is skipped when step 7's incremental download
    found no new PortWatch data (PortWatch publishes weekly on Tuesday EST,
    so most days return zero new rows). Override with --force-shipping.
    Skip the whole shipping block (steps 7+8) with --skip-shipping-pipeline.

Narrative trigger gate:
    Steps 11 + 12 are skipped automatically when no curated trigger series has
    moved by more than its 2σ threshold (computed from 2025 data) AND the
    last narrative is less than 7 days old. Override with --force-narratives.
    Inspect what would fire with --show-trigger-state.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent  # Iran Monitor/ (script is at Iran Monitor/scripts/energy/)
sys.path.insert(0, str(PROJECT_ROOT))

from src.db import (
    DB_PATH,
    comtrade_dep_partition_exists,
    get_connection,
    get_metadata,
    init_db,
    replace_series,
    replace_singstat_trade,
    replace_trade,
    upsert_comtrade_dep_partition,
    upsert_metadata,
)
from src.series_config import SERIES_REGISTRY
from src.derived_series import (
    compute_mas_core_mom,
    compute_singstat_chem_export_country_series,
    compute_singstat_petroleum_export_country_series,
    compute_sg_me_import_shares,
    compute_sg_import_monthly_aggregates,
    compute_sg_chem_export_regional_shares,
    compute_sg_chem_export_monthly_aggregates,
    compute_regional_chem_share_from_sg,
    compute_regional_chem_levels,
    compute_regional_fuel_share_from_sg,
    compute_regional_fuel_levels,
    compute_fx_indexed,
    compute_rubber_tsr20_usc,
    compute_singapore_shipping_nowcast,
)
from src.country_mapping import display_name as country_display, iso2 as country_iso2
# Financial markets fetchers — yfinance / ADB / investing.com.
# Lives in scripts/energy/ rather than src/ because it does network I/O
# (matches the placement of fetch_comtrade_regional_dep below).
sys.path.insert(0, str(Path(__file__).resolve().parent))
from financial_markets_fetchers import (   # noqa: E402
    fetch_yfinance_financial_markets,
    fetch_adb_bond_yields,
    fetch_investing_commodities,
)

# ---------------------------------------------------------------------------
# .env loader
# ---------------------------------------------------------------------------

def load_env(env_path: Path) -> None:
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


# Iran Monitor's local .env (copied from ME Dashboard for self-containment).
# Fall back to the ME Dashboard .env if the local copy is missing — defensive
# only; `.env` should normally live in Iran Monitor/.
load_env(PROJECT_ROOT / ".env")
load_env(Path("/Users/kevinlim/Documents/MAS/Projects/ESD/Middle East Dashboard/.env"))


# ---------------------------------------------------------------------------
# CEIC fetcher
# ---------------------------------------------------------------------------

def fetch_ceic_series() -> dict[str, pd.DataFrame]:
    """Fetch all CEIC-sourced series from the registry."""
    from ceic_api_client.pyceic import Ceic

    username = os.environ.get("CEIC_USERNAME", "")
    password = os.environ.get("CEIC_PASSWORD", "")

    if not username or not password:
        print("  SKIP: CEIC credentials not set (CEIC_USERNAME / CEIC_PASSWORD)")
        return {}

    print(f"  Logging in as {username}...")
    Ceic.login(username, password)
    print("  Login OK")

    frames: dict[str, pd.DataFrame] = {}
    ceic_series = {
        sid: sdef for sid, sdef in SERIES_REGISTRY.items() if sdef.get("source") == "ceic"
    }

    for series_id, series_def in ceic_series.items():
        source_key = series_def["source_key"]
        label = series_def.get("label", series_id)
        unit = series_def.get("unit", "")
        frequency = series_def.get("frequency", "")

        try:
            result = Ceic.series_data(str(source_key))
            if not hasattr(result, "data") or not result.data:
                print(f"    EMPTY  {source_key}  {label}")
                continue

            time_points = getattr(result.data[0], "time_points", []) or []
            if not time_points:
                print(f"    EMPTY  {source_key}  {label}  (no time points)")
                continue

            rows = [{"date": tp.date, "value": tp.value} for tp in time_points]
            df = pd.DataFrame(rows)
            df["date"] = pd.to_datetime(df["date"], errors="coerce")
            df["value"] = pd.to_numeric(df["value"], errors="coerce")
            df = df.dropna(subset=["date", "value"]).sort_values("date").reset_index(drop=True)

            df["series_id"] = series_id
            df["series_name"] = label
            df["source"] = "ceic"
            df["unit"] = unit
            df["frequency"] = frequency

            frames[series_id] = df
            print(f"    OK     {source_key}  {label:30s}  {len(df)} pts")

        except Exception as exc:
            print(f"    FAIL   {source_key}  {label:30s}  {exc}")

    return frames


# ---------------------------------------------------------------------------
# Google Sheets fetcher (for Bloomberg data)
# ---------------------------------------------------------------------------
#
# 2026-04-28 — refactored for the "dashboard data v2" sheet layout. Old layout
# had three frequency-keyed tabs (Daily/Weekly/Monthly) with rows
#   0: Bloomberg ticker, 1: series name, 2: unit, 3: blank, 4+: data
# New layout is two content-keyed tabs ("Refined Product Prices",
# "Industrial Input Prices") with rows
#   0: series name, 1: unit, 2: frequency (per-series), 3+: data (DD-MM-YY)
# Series_id pattern is now name-based ("gsheets_<slug>") instead of including
# the tab name — see resolve_node_to_series_ids() in build_iran_monitor.py for
# the matching resolver. The two trade tabs (SG_Annual_Imports,
# SG_Monthly_Imports) are handled separately by fetch_singstat_trade_from_gsheets.

import re

SHEET_PRICE_TABS = ("Refined Product Prices", "Industrial Input Prices",
                    "SG Financial Markets")
NAME_ROW_INDEX = 0
UNIT_ROW_INDEX = 1
FREQ_ROW_INDEX = 2
DATA_START_ROW_INDEX = 3


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
        raise RuntimeError(
            "Set GOOGLE_SERVICE_ACCOUNT_JSON (raw JSON string) or "
            "GOOGLE_SERVICE_ACCOUNT_FILE (path to JSON key file) in .env"
        )

    creds = Credentials.from_service_account_info(
        info, scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"]
    )
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


def _pad_rows(rows: list[list[str]]) -> list[list[str]]:
    max_width = max((len(r) for r in rows), default=0)
    return [r + [""] * (max_width - len(r)) for r in rows]


def _parse_sheet_tab(sheet_name: str, rows: list[list[str]]) -> pd.DataFrame:
    """Parse a price tab from the new (dashboard data v2) sheet layout.

    Layout:
      row 0: series name (col 0 = "Name")
      row 1: unit         (col 0 = "Units")
      row 2: frequency    (col 0 = "Frequency") — per-series, NOT tab-derived
      row 3+: date in col 0 (DD-MM-YY), values in subsequent cols
    """
    if len(rows) <= DATA_START_ROW_INDEX:
        return pd.DataFrame()

    padded = _pad_rows(rows)
    name_row = padded[NAME_ROW_INDEX]
    unit_row = padded[UNIT_ROW_INDEX]
    freq_row = padded[FREQ_ROW_INDEX]

    records: list[dict[str, Any]] = []
    for col_idx in range(1, len(name_row)):
        series_name = str(name_row[col_idx]).strip()
        if not series_name:
            continue
        unit = str(unit_row[col_idx]).strip()
        # Frequency is now per-series (row 2). If blank, assume Daily — the
        # safest default for this dataset since most rows are price ticks.
        freq = str(freq_row[col_idx]).strip() or "Daily"

        for row in padded[DATA_START_ROW_INDEX:]:
            raw_date = str(row[0]).strip()
            raw_value = str(row[col_idx]).strip() if col_idx < len(row) else ""
            # New sheet has #N/A cells where Bloomberg returned no data —
            # filter them out so they don't pollute the time series.
            if not raw_date or not raw_value or raw_value.upper() in ("#N/A", "N/A", "-"):
                continue
            records.append({
                "date": raw_date,
                "value": raw_value,
                "series_name": series_name,
                "unit": unit,
                "frequency": freq,
            })

    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records)
    # New date format: DD-MM-YY (e.g. "01-01-25").
    df["date"] = pd.to_datetime(df["date"], format="%d-%m-%y", errors="coerce")
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df.dropna(subset=["date", "value"]).sort_values(["series_name", "date"]).reset_index(drop=True)



# Unit conversions applied after Google Sheets ingestion.
# Each entry: (series_name_substring, from_unit, to_unit, multiplier)
GSHEETS_UNIT_CONVERSIONS = [
    ("US Gulf Ethylene", "USD/pound", "USD/metric tonne", 2204.62),
]


def _apply_gsheets_unit_conversions(frames: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """Convert known series that arrive in non-standard units."""
    for sid, df in frames.items():
        for name_substr, from_unit, to_unit, multiplier in GSHEETS_UNIT_CONVERSIONS:
            if (
                name_substr.lower() in df["series_name"].iloc[0].lower()
                and df["unit"].iloc[0].strip().lower() == from_unit.lower()
            ):
                df = df.copy()
                df["value"] = df["value"] * multiplier
                df["unit"] = to_unit
                frames[sid] = df
                print(f"    CONV   {df['series_name'].iloc[0]}: {from_unit} -> {to_unit} (×{multiplier})")
                break
    return frames


def _gsheets_slug(name: str, max_len: int = 55) -> str:
    """Stable slug for series_id from a Bloomberg series name. Lowercased,
    non-alphanumerics collapsed to single underscore, capped to max_len so the
    full id ('gsheets_<slug>') stays under SQLite-friendly lengths."""
    slug = re.sub(r'[^A-Za-z0-9]+', '_', name).strip('_').lower()
    return slug[:max_len].rstrip('_')


def fetch_google_sheets_series() -> dict[str, pd.DataFrame]:
    """Fetch Bloomberg-sourced commodity price data from Google Sheets.

    Reads the two price tabs of "dashboard data v2" — tab is now a content
    classification (refined products vs industrial inputs), not a frequency
    bucket. Frequency is read per-series from row 2 of each tab.

    series_id is name-based and tab-independent ('gsheets_<slug>'), so future
    tab reorganisations don't change the keys downstream consumers see.
    """
    spreadsheet_id = os.environ.get("GOOGLE_SHEETS_SPREADSHEET_ID", "")
    if not spreadsheet_id:
        print("  SKIP: GOOGLE_SHEETS_SPREADSHEET_ID not set")
        return {}

    try:
        service = _get_sheets_service()
    except Exception as exc:
        print(f"  SKIP: Google Sheets auth failed: {exc}")
        return {}

    frames: dict[str, pd.DataFrame] = {}

    for tab_name in SHEET_PRICE_TABS:
        try:
            result = (
                service.spreadsheets().values()
                .get(spreadsheetId=spreadsheet_id, range=tab_name)
                .execute()
            )
            rows = result.get("values", [])
            df = _parse_sheet_tab(tab_name, rows)

            if df.empty:
                print(f"    EMPTY  {tab_name} tab")
                continue

            # One entry per unique series_name in this tab. series_id is now
            # tab-independent — based purely on the series name.
            for series_name in df["series_name"].unique():
                series_df = df[df["series_name"] == series_name].copy()
                series_id = f"gsheets_{_gsheets_slug(series_name)}"
                series_df["series_id"] = series_id
                series_df["source"] = "google_sheets"
                frames[series_id] = series_df
                freq = series_df["frequency"].iloc[0]
                print(f"    OK     {tab_name:24s}  {freq:7s}  {series_name[:50]:50s}  {len(series_df)} pts")

        except Exception as exc:
            print(f"    FAIL   {tab_name} tab: {exc}")

    # Apply unit conversions for series stored in non-standard units
    frames = _apply_gsheets_unit_conversions(frames)

    return frames


# ---------------------------------------------------------------------------
# SingStat trade fetcher (3 long-format tabs in the same Google Sheet)
# ---------------------------------------------------------------------------
#
# The "dashboard data v2" sheet has three trade tabs alongside the price tabs:
#
#   SG_Annual_Imports  — long format, country × annual values, with a SITC
#                        column (mostly SITC 3 family — mineral fuels and
#                        sub-codes 333 crude petroleum, 334 refined products,
#                        etc.). Header row at row 0.
#   SG_Monthly_Imports — same long-format, but column headers are months
#                        ("Apr - 2025", "May - 2025", ...).
#   SG_Chemicals_DX    — Singapore's Domestic eXports of chemicals, by
#                        destination. Hybrid layout: rows 0-1 are title +
#                        unit, row 2 blank, row 3 is a 2-tier header
#                        ("ANNUAL" spans 3 cols, "2026 MONTHLY" spans the
#                        rest), row 4 is per-column period labels (years +
#                        "Jan-2026" / "Feb-2026" / ...), row 5+ is data.
#
# All three are written into the trade_singstat table. Values are SGD
# thousands as published. Dates are normalised to YYYY-MM-DD (annual = Dec 31
# of the year; monthly = first of the month).

SHEET_TRADE_IMPORT_ANNUAL  = "SG_Annual_Imports"
SHEET_TRADE_IMPORT_MONTHLY = "SG_Monthly_Imports"
SHEET_TRADE_CHEMICALS_DX   = "SG_Chemicals_DX"
SHEET_TRADE_PETROLEUM_DX   = "SG_Petroleum_DX"   # SITC 334 refined petroleum

# Friendly labels for SITC codes seen in the imports tabs. Anything not in
# this dict gets product_label = f"SITC {code}".
SITC_LABELS = {
    "3":   "Mineral Fuels (total)",
    "32":  "Coal, Coke & Briquettes",
    "33":  "Petroleum, Petroleum Products",
    "333": "Crude Petroleum Oils",
    "334": "Refined Petroleum Products",
    "335": "Residual Petroleum & Waxes",
    "34":  "Gas (natural & manufactured)",
    "341": "Gas, Natural & Manufactured",
    "342": "LPG (Liquefied Propane & Butane)",
    "343": "Natural Gas",
    "5":   "Chemicals (total)",
}


def _sitc_label(code: str) -> str:
    return SITC_LABELS.get(code, f"SITC {code}" if code else "")


def _clean_singstat_number(raw: str) -> float | None:
    """Parse '14,332,346' → 14332346.0. Returns None on '-' or empty."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s or s in ("-", "—", "..", "N/A", "n.a."):
        return None
    try:
        return float(s.replace(",", ""))
    except (TypeError, ValueError):
        return None


def _period_for_year(year: int) -> str:
    """Annual period stored as Dec 31 of the year for chronological sorting."""
    return f"{year:04d}-12-31"


def _parse_month_label(label: str) -> str | None:
    """Parse 'Apr - 2025', 'Jan-2026', 'Mar 2026', 'May - 2025' → 'YYYY-MM-01'."""
    import re
    if not label:
        return None
    s = re.sub(r"\s+", " ", str(label).strip())
    # Try explicit "Mon - YYYY" / "Mon-YYYY" / "Mon YYYY" forms
    m = re.match(r"^([A-Za-z]{3,9})\s*[- ]\s*(\d{4})$", s)
    if not m:
        return None
    mon_name, year = m.group(1), int(m.group(2))
    try:
        # %b parses 'Jan'..'Dec' (case-insensitive via title())
        from datetime import datetime
        dt = datetime.strptime(f"{mon_name.title()[:3]} {year}", "%b %Y")
        return dt.strftime("%Y-%m-01")
    except ValueError:
        return None


def _parse_year_label(label: str) -> str | None:
    """Parse '2023' / '2024' → '2023-12-31'. Returns None if not a 4-digit year."""
    s = str(label).strip()
    if len(s) == 4 and s.isdigit():
        return _period_for_year(int(s))
    return None


def _enrich_with_country(records: list[dict]) -> None:
    """Mutate each record in-place: add partner_iso2 + partner_display."""
    for r in records:
        r["partner_iso2"] = country_iso2(r["partner_name"])
        r["partner_display"] = country_display(r["partner_name"])


def _parse_singstat_imports_tab(tab_name: str, rows: list[list[str]]) -> pd.DataFrame:
    """Parse SG_Annual_Imports or SG_Monthly_Imports.

    Layout (long format):
      row 0: ["COUNTRY/MARKET", "SITC", "Units", <period_1>, <period_2>, ...]
      row 1+: [partner_name, sitc_code, units_label, value_1, value_2, ...]
    """
    if not rows or len(rows) < 2:
        return pd.DataFrame()
    header = rows[0]
    if len(header) < 4:
        return pd.DataFrame()

    # Column index → period (YYYY-MM-DD). Try year first, then month.
    period_for_col: dict[int, str] = {}
    for col_idx, lbl in enumerate(header):
        if col_idx < 3:
            continue
        per = _parse_year_label(lbl) or _parse_month_label(lbl)
        if per:
            period_for_col[col_idx] = per

    if not period_for_col:
        return pd.DataFrame()

    is_monthly = any(p.endswith("-01") and not p.endswith("-12-31") for p in period_for_col.values())
    frequency = "Monthly" if is_monthly else "Annual"

    records: list[dict] = []
    for row in rows[1:]:
        if not row or len(row) < 4:
            continue
        partner_raw = str(row[0]).strip() if row[0] else ""
        sitc_code = str(row[1]).strip() if len(row) > 1 and row[1] else ""
        if not partner_raw or not sitc_code:
            continue
        # Skip aggregate rows (we want per-country detail).
        if partner_raw.upper().startswith(("TOTAL FOR OTHER COUNTRIES", "TOTAL FOR ALL", "ALL COUNTRIES")):
            continue
        product_code = f"SITC_{sitc_code}"
        product_label = _sitc_label(sitc_code)
        for col_idx, period in period_for_col.items():
            if col_idx >= len(row):
                continue
            val = _clean_singstat_number(row[col_idx])
            if val is None:
                continue
            records.append({
                "period":         period,
                "frequency":      frequency,
                "flow":           "Imports",
                "product_code":   product_code,
                "product_label":  product_label,
                "partner_name":   partner_raw,
                "value_sgd_thou": val,
            })

    _enrich_with_country(records)
    if not records:
        return pd.DataFrame()
    return pd.DataFrame(records)


def _parse_singstat_chemicals_dx_tab(
    rows: list[list[str]],
    *,
    product_code: str = "SITC_5_excl_51_54",
    product_label: str = "Chemicals (excl. organics & pharma)",
) -> pd.DataFrame:
    """Parse a SingStat domestic-exports-by-market hybrid annual+monthly tab.

    Used for both `SG_Chemicals_DX` (SITC 5 less SITC 51 less SITC 54) and
    `SG_Petroleum_DX` (SITC 334 — refined petroleum) — same layout, different
    product code/label. The `product_code` and `product_label` parameters
    are written into every row so downstream consumers can filter cleanly.

    Layout (identical for both tabs):
      row 0: ["SINGAPORE'S … FOR <commodity>"]    (title, varies)
      row 1: ["VALUE IN S$ THOUSANDS"]             (unit)
      row 2: []                                    (blank)
      row 3: 2-tier header — ["COUNTRY/MARKET", "ANNUAL", "", "", "2026 MONTHLY", ...]
      row 4: per-column period labels — ["", "2023", "2024", "2025", "Jan-2026", ...]
      row 5+: [country, val_2023, val_2024, val_2025, val_jan, val_feb, val_mar, ...]
    """
    if not rows or len(rows) < 6:
        return pd.DataFrame()

    # Row 4 is the per-column period label row.
    period_row = rows[4]
    period_for_col: dict[int, tuple[str, str]] = {}  # col_idx -> (period, freq)
    for col_idx, lbl in enumerate(period_row):
        if col_idx == 0:
            continue
        per_year = _parse_year_label(lbl)
        if per_year:
            period_for_col[col_idx] = (per_year, "Annual")
            continue
        per_month = _parse_month_label(lbl)
        if per_month:
            period_for_col[col_idx] = (per_month, "Monthly")

    if not period_for_col:
        return pd.DataFrame()

    records: list[dict] = []
    for row in rows[5:]:
        if not row:
            continue
        partner_raw = str(row[0]).strip() if row[0] else ""
        if not partner_raw:
            continue
        if partner_raw.upper().startswith(("TOTAL FOR OTHER COUNTRIES", "TOTAL", "ALL COUNTRIES")):
            continue
        for col_idx, (period, freq) in period_for_col.items():
            if col_idx >= len(row):
                continue
            val = _clean_singstat_number(row[col_idx])
            if val is None:
                continue
            records.append({
                "period":         period,
                "frequency":      freq,
                "flow":           "Exports",
                # product_code and product_label are caller-supplied so
                # the same parser handles both chemicals (SITC 5 less 51
                # less 54) and refined petroleum (SITC 334).
                "product_code":   product_code,
                "product_label":  product_label,
                "partner_name":   partner_raw,
                "value_sgd_thou": val,
            })

    _enrich_with_country(records)
    if not records:
        return pd.DataFrame()
    return pd.DataFrame(records)


def fetch_singstat_trade_from_gsheets() -> pd.DataFrame:
    """Pull the 3 SingStat trade tabs from the dashboard sheet and return a
    single long-format DataFrame ready for replace_singstat_trade()."""
    spreadsheet_id = os.environ.get("GOOGLE_SHEETS_SPREADSHEET_ID", "")
    if not spreadsheet_id:
        print("  SKIP: GOOGLE_SHEETS_SPREADSHEET_ID not set")
        return pd.DataFrame()
    try:
        service = _get_sheets_service()
    except Exception as exc:
        print(f"  SKIP: Google Sheets auth failed: {exc}")
        return pd.DataFrame()

    from functools import partial
    frames: list[pd.DataFrame] = []

    # Each tab tuple is (tab_name, parser, takes_tab_name).
    # `takes_tab_name=True` means the parser's signature is (tab_name, rows);
    # False means just (rows). The chemicals/petroleum DX tabs share one
    # parser parameterised via product_code/product_label (functools.partial).
    for tab_name, parser, takes_tab_name in (
        (SHEET_TRADE_IMPORT_ANNUAL,  _parse_singstat_imports_tab, True),
        (SHEET_TRADE_IMPORT_MONTHLY, _parse_singstat_imports_tab, True),
        (SHEET_TRADE_CHEMICALS_DX,
         partial(_parse_singstat_chemicals_dx_tab,
                 product_code="SITC_5_excl_51_54",
                 product_label="Chemicals (excl. organics & pharma)"),
         False),
        (SHEET_TRADE_PETROLEUM_DX,
         partial(_parse_singstat_chemicals_dx_tab,
                 product_code="SITC_334",
                 product_label="Refined petroleum (SITC 334)"),
         False),
    ):
        try:
            result = (
                service.spreadsheets().values()
                .get(spreadsheetId=spreadsheet_id, range=tab_name)
                .execute()
            )
            rows = result.get("values", [])
            if takes_tab_name:
                df = parser(tab_name, rows)
            else:
                df = parser(rows)
            if df.empty:
                print(f"    EMPTY  {tab_name}")
                continue
            n_rows  = len(df)
            n_part  = df["partner_name"].nunique()
            n_per   = df["period"].nunique()
            n_prod  = df["product_code"].nunique()
            print(f"    OK     {tab_name:22s}  {n_rows:>5d} rows  "
                  f"({n_part} partners × {n_per} periods × {n_prod} products)")
            frames.append(df)
        except Exception as exc:
            print(f"    FAIL   {tab_name}: {exc}")

    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


# ---------------------------------------------------------------------------
# UN Comtrade fetcher (partner-level monthly trade)
# ---------------------------------------------------------------------------

COMTRADE_URL = "https://comtradeapi.un.org/data/v1/get/C/M/HS"
COMTRADE_REPORTER = "702"       # Singapore
COMTRADE_REPORTER_NAME = "Singapore"
COMTRADE_REPORTER_ISO3 = "SGP"
COMTRADE_HS_CODES = ["2709", "2710", "2711", "2902", "2907"]
COMTRADE_YEARS_BACK = 5          # rolling 5-year window (monthly)
COMTRADE_FLOWS = {"M": "Imports", "X": "Exports"}


def _comtrade_periods(years_back: int) -> list[str]:
    """Return YYYYMM strings for the last `years_back` years through this month."""
    today = datetime.now(timezone.utc).date()
    start_year = today.year - years_back
    periods: list[str] = []
    year = start_year
    month = today.month + 1 if start_year < today.year else 1
    # Walk forward month-by-month from (start_year, start_month) up to current month
    current = datetime(start_year, today.month, 1).date() if start_year < today.year else datetime(today.year, 1, 1).date()
    # Simpler: enumerate every month in the window [start_year-01 .. today.year-today.month]
    periods = []
    for yr in range(start_year, today.year + 1):
        last_month = 12 if yr < today.year else today.month
        for mo in range(1, last_month + 1):
            periods.append(f"{yr}{mo:02d}")
    return periods


def _chunk(seq: list, size: int) -> list[list]:
    return [seq[i : i + size] for i in range(0, len(seq), size)]


def _comtrade_get_with_retry(url: str, params: dict, headers: dict, *, max_retries: int = 4):
    """GET with exponential backoff on 429 / 5xx / read timeouts."""
    import time
    import requests

    delay = 2.0
    last_exc = None
    for attempt in range(max_retries):
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=60)
        except requests.exceptions.RequestException as exc:
            last_exc = exc
            time.sleep(delay)
            delay *= 2
            continue
        if resp.status_code == 200:
            return resp
        if resp.status_code in (429, 500, 502, 503, 504):
            # Respect Retry-After if provided
            retry_after = resp.headers.get("Retry-After")
            wait = float(retry_after) if retry_after and retry_after.isdigit() else delay
            time.sleep(wait)
            delay *= 2
            continue
        # Non-retryable
        return resp
    if last_exc:
        raise last_exc
    return resp  # last response even if retries exhausted


def fetch_trade_from_comtrade() -> pd.DataFrame:
    """Pull monthly Singapore trade for the configured HS codes and flows.

    Returns a dataframe with columns matching the `trade` table schema.
    """
    import time

    api_key = os.environ.get("COMTRADE_API_KEY", "")
    if not api_key:
        print("  SKIP: COMTRADE_API_KEY not set")
        return pd.DataFrame()

    headers = {"Ocp-Apim-Subscription-Key": api_key, "Accept": "application/json"}
    periods = _comtrade_periods(COMTRADE_YEARS_BACK)

    # Comtrade accepts comma-separated periods; 12 per call keeps URL short.
    period_chunks = _chunk(periods, 12)

    all_rows: list[dict] = []
    for flow_code, flow_name in COMTRADE_FLOWS.items():
        for hs in COMTRADE_HS_CODES:
            for chunk_idx, period_chunk in enumerate(period_chunks):
                params = {
                    "reporterCode": COMTRADE_REPORTER,
                    "period": ",".join(period_chunk),
                    "cmdCode": hs,
                    "flowCode": flow_code,
                    "includeDesc": "true",
                }
                try:
                    resp = _comtrade_get_with_retry(COMTRADE_URL, params, headers)
                    if resp.status_code != 200:
                        print(f"    FAIL   HS {hs}  flow={flow_name}  chunk {chunk_idx}: HTTP {resp.status_code} {resp.text[:120]}")
                        continue
                    rows = (resp.json() or {}).get("data", []) or []
                except Exception as exc:
                    print(f"    FAIL   HS {hs}  flow={flow_name}  chunk {chunk_idx}: {exc}")
                    continue
                # Small gap between calls to stay below ~1 req/sec
                time.sleep(0.4)

                for r in rows:
                    # Skip the "World" aggregate partner so the dashboard works at
                    # partner-level; we'll reaggregate in the UI if needed.
                    if r.get("partnerCode") == 0:
                        continue
                    period = str(r.get("period", "")).strip()
                    if len(period) != 6 or not period.isdigit():
                        continue
                    year = int(period[:4])
                    month = int(period[4:])
                    partner_iso3 = str(r.get("partnerISO", "")).strip() or None
                    partner_name = str(r.get("partnerDesc", "")).strip()
                    if not partner_name:
                        continue
                    # Comtrade primaryValue is in USD (not thousands). Convert to
                    # thousands so the dashboard's "TradeValue in 1000 USD" column
                    # keeps its existing semantics.
                    raw_value = r.get("primaryValue")
                    try:
                        trade_value = float(raw_value) / 1000.0
                    except (TypeError, ValueError):
                        continue

                    all_rows.append({
                        "period": f"{year}-{month:02d}",
                        "year": year,
                        "month": month,
                        "nomenclature": f"HS {r.get('classificationCode', 'H6')}",
                        "reporter_iso3": COMTRADE_REPORTER_ISO3,
                        "product_code": str(r.get("cmdCode", hs)).strip(),
                        "reporter_name": COMTRADE_REPORTER_NAME,
                        "partner_name": partner_name,
                        "partner_iso3": partner_iso3,
                        "trade_flow_name": flow_name,
                        "trade_flow_code": 1 if flow_code == "M" else 2,
                        "trade_value": trade_value,
                    })

            print(f"    OK     HS {hs:5s}  flow={flow_name:7s}  running total {len(all_rows):>6d} rows")

    if not all_rows:
        return pd.DataFrame()

    df = pd.DataFrame(all_rows)
    # Dedupe in case any period chunks overlapped
    df = df.drop_duplicates(
        subset=["period", "product_code", "partner_name", "trade_flow_name"]
    ).reset_index(drop=True)
    return df


# ---------------------------------------------------------------------------
# SingStat merchandise trade fetcher (SITC-level monthly totals)
# ---------------------------------------------------------------------------
#
# SingStat Table Builder publishes per-row data via a two-step lookup that
# isn't documented in the public API reference but is what the web UI itself
# uses (discovered by inspecting tablebuilder.singstat.gov.sg network traffic):
#
#   1. GET /api/doswebcontent/1/StatisticTableFileUpload/StatisticTable/{tableId}
#      -> Data.id is the table GUID (changes when SingStat republishes).
#   2. GET /rowdata/{guid}_{tableId}_{seriesNo}.json
#      -> flat list of {"Key": "YYYY MMM", "Value": "<number>"} spanning the
#         full history of that row. No date-range or filter params needed.
#
# seriesNo uses dotted positions like "2.1.1" = Imports > Oil > Petroleum
# (flow 2 = Imports, flow 3 = Total Exports, flow 4 = Domestic Exports,
# flow 5 = Re-Exports; .1 = Oil, .1.1 = Petroleum, .1.2 = Oil Bunkers).

SINGSTAT_META_URL = (
    "https://tablebuilder.singstat.gov.sg/api/doswebcontent/1/"
    "StatisticTableFileUpload/StatisticTable/{table_id}"
)
SINGSTAT_ROW_URL = (
    "https://tablebuilder.singstat.gov.sg/rowdata/{guid}_{table_id}_{series_no}.json"
)
SINGSTAT_YEARS_BACK = 5
# SingStat's API blocks requests without a browser UA.
SINGSTAT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
}


def _singstat_get_table_guid(table_id: str, cache: dict[str, str]) -> str | None:
    """Look up the current GUID (titleId) for a SingStat table."""
    import requests

    if table_id in cache:
        return cache[table_id]
    url = SINGSTAT_META_URL.format(table_id=table_id)
    try:
        resp = requests.get(url, headers=SINGSTAT_HEADERS, timeout=30)
        if resp.status_code != 200:
            print(f"    GUID   {table_id}: HTTP {resp.status_code} {resp.text[:200]}")
            return None
        payload = resp.json() or {}
    except Exception as exc:
        print(f"    GUID   {table_id}: {exc}")
        return None

    data = payload.get("Data") or {}
    guid = data.get("id") or data.get("titleId")
    if not guid:
        print(f"    GUID   {table_id}: no id/titleId in metadata response")
        return None
    cache[table_id] = guid
    return guid


# ---------------------------------------------------------------------------
# Comtrade regional dependence ingestor — chemicals + mineral fuels
# ---------------------------------------------------------------------------
#
# Pulls partner-level imports of selected SITC chapters for each of the 10
# regional countries, annually. Stored in trade_comtrade_dep so the renderer
# can compute exposure ratios at chart time (e.g., "Malaysia's ME share of
# mineral fuel imports", "Indonesia's SG share of chemical imports") without
# the ingest committing to a specific partner subset.
#
# Quota: 10 reporters × 7 SITC × 3 years = 210 calls per full ingest.
# Comtrade Plus free tier is ~250-500 calls/day. The --only-stale flag (or
# the COMTRADE_DEP_ONLY_STALE env var) skips (reporter, sitc, year) triples
# already in the DB so a rate-limited rerun resumes cleanly.

COMTRADE_DEP_URL = "https://comtradeapi.un.org/data/v1/get/C/A/S4"

# Reporter ISO2 → (display_name, Comtrade reporterCode)
COMTRADE_DEP_REPORTERS = {
    "CN": ("China",       "156"),
    "IN": ("India",       "699"),
    "ID": ("Indonesia",   "360"),
    "JP": ("Japan",       "392"),
    "MY": ("Malaysia",    "458"),
    "PH": ("Philippines", "608"),
    "KR": ("South Korea", "410"),
    "TW": ("Taiwan",      "490"),
    "TH": ("Thailand",    "764"),
    "VN": ("Vietnam",     "704"),
}

# SITC Rev 4 codes we care about. Chemicals first (5 minus 51 minus 54),
# then mineral fuels (3 plus the 333/334/343 sub-breakdowns matching what
# the SG_Annual_Imports sheet exposes).
COMTRADE_DEP_SITC_CODES = ["5", "51", "54", "3", "333", "334", "343"]

COMTRADE_DEP_YEARS = ["2023", "2024"]   # 2025 dropped — only 3 of 10 reporters
                                         # had 2025 data as of 2026-04-29 (in
                                         # both SITC-Annual and HS-Annual modes;
                                         # see REGIONAL_TRADE_NOTES.md §4 / 7a.1).
                                         # Will auto-fill on subsequent runs as
                                         # Comtrade publishes more reporters.

# Polite gap between calls. Comtrade Plus free tier rate-limits aggressively
# and the retry/backoff handler below kicks in if we still hit 429s.
COMTRADE_DEP_INTER_CALL_SLEEP_SEC = 1.5
COMTRADE_DEP_MAX_RETRIES = 5


def _comtrade_dep_get(params: dict, headers: dict) -> "tuple[int, dict | None]":
    """One Comtrade GET with exponential backoff on 429/5xx. Returns
    (http_status, json_payload_or_None)."""
    import requests
    delay = 2.0
    for _ in range(COMTRADE_DEP_MAX_RETRIES):
        try:
            resp = requests.get(COMTRADE_DEP_URL, params=params, headers=headers, timeout=60)
        except requests.exceptions.RequestException:
            time.sleep(delay)
            delay *= 2
            continue
        if resp.status_code == 200:
            try:
                return 200, resp.json()
            except Exception:
                return 200, None
        if resp.status_code in (429, 500, 502, 503, 504):
            ra = resp.headers.get("Retry-After")
            wait = float(ra) if ra and ra.isdigit() else delay
            time.sleep(wait)
            delay *= 2
            continue
        return resp.status_code, None
    return 429, None


def _comtrade_dep_aggregate_response(payload: dict) -> dict[str, tuple[str, float]]:
    """Reduce a raw Comtrade response (one (reporter,sitc,year), all partners)
    into a flat mapping partner_iso3 → (partner_name, summed_value_usd).

    Multiple raw rows can share the same partner — Comtrade splits along
    `partner2Code` and possibly other dimensions even when we set
    partner2Code=0. We collapse all rows for a given partner_iso3 by summing
    primaryValue. (We verified in the diagnostic probe that summing all rows
    for India 2024 gave sensible totals: World $157.7B, China $44.2B, SG
    $4.9B, with China + SG well under World.)
    """
    import time as _time  # silence unused-warning if reorg; keep import scope local
    result: dict[str, list] = {}
    for r in (payload or {}).get("data", []) or []:
        partner_iso = r.get("partnerISO") or r.get("partnerCode") or ""
        partner_name = r.get("partnerDesc") or partner_iso
        val = r.get("primaryValue")
        if not partner_iso or not isinstance(val, (int, float)):
            continue
        slot = result.setdefault(str(partner_iso), [partner_name, 0.0])
        slot[1] += float(val)
    return {iso: (name, total) for iso, (name, total) in result.items()}


def fetch_comtrade_regional_dep(conn, *, only_stale: bool = True) -> dict[str, int]:
    """Fetch partner-level annual SITC imports for the 10 regional reporters.

    Returns a counters dict: {'fetched_calls', 'skipped_calls', 'rows_written',
    'failures'}.

    only_stale=True (default) skips (reporter, sitc, year) combinations
    already present in trade_comtrade_dep — restartable across days when
    Comtrade rate-limiting forces partial completion.
    """
    api_key = os.environ.get("COMTRADE_API_KEY", "")
    if not api_key:
        print("  SKIP: COMTRADE_API_KEY not set")
        return {"fetched_calls": 0, "skipped_calls": 0, "rows_written": 0, "failures": 0}

    headers = {"Ocp-Apim-Subscription-Key": api_key, "Accept": "application/json"}

    fetched_calls = 0
    skipped_calls = 0
    rows_written = 0
    failures = 0
    empty_responses: list[tuple[str, str, str]] = []   # (iso2, year, sitc) tuples

    total = len(COMTRADE_DEP_REPORTERS) * len(COMTRADE_DEP_SITC_CODES) * len(COMTRADE_DEP_YEARS)
    call_idx = 0

    for iso2, (name, reporter_code) in COMTRADE_DEP_REPORTERS.items():
        for year in COMTRADE_DEP_YEARS:
            period = f"{year}-12-31"
            for sitc in COMTRADE_DEP_SITC_CODES:
                call_idx += 1
                if only_stale and comtrade_dep_partition_exists(conn, period, iso2, sitc):
                    skipped_calls += 1
                    continue

                params = {
                    "reporterCode": reporter_code,
                    "period":       year,
                    "cmdCode":      sitc,
                    "flowCode":     "M",          # Imports
                    "partner2Code": "0",          # collapse secondary-partner dimension
                    "includeDesc":  "true",
                    # No partnerCode → returns all partners (one row each).
                }
                status, payload = _comtrade_dep_get(params, headers)
                if status != 200 or not payload:
                    failures += 1
                    print(f"    [{call_idx:3d}/{total}]  {iso2} {year} SITC {sitc:<4s}  FAIL  status={status}")
                    time.sleep(COMTRADE_DEP_INTER_CALL_SLEEP_SEC)
                    continue

                # Reduce to partner_iso3 → (name, total)
                partner_totals = _comtrade_dep_aggregate_response(payload)
                if not partner_totals:
                    # IMPORTANT: do NOT mark empty responses as ingested.
                    # Many reporters publish 2025 trade data months late
                    # (Comtrade lag can run 6-12 months). If we wrote a
                    # zero-row partition, the only_stale check would skip
                    # this combination forever even after data appears.
                    # Leaving it un-ingested means each rerun retries.
                    empty_responses.append((iso2, year, sitc))
                    print(f"    [{call_idx:3d}/{total}]  {iso2} {year} SITC {sitc:<4s}  EMPTY (no data — will retry on next run)")
                    fetched_calls += 1
                    time.sleep(COMTRADE_DEP_INTER_CALL_SLEEP_SEC)
                    continue

                rows_to_write = [(iso3, name_, val) for iso3, (name_, val) in partner_totals.items()]
                n = upsert_comtrade_dep_partition(conn, period, iso2, sitc, rows_to_write)
                conn.commit()
                rows_written += n
                fetched_calls += 1

                # Show partner count + World total + SG share for live progress
                world = partner_totals.get("W00", ("World", 0.0))[1]
                sg    = partner_totals.get("SGP", ("Singapore", 0.0))[1]
                share = (sg / world * 100) if world > 0 else 0
                print(f"    [{call_idx:3d}/{total}]  {iso2} {year} SITC {sitc:<4s}  "
                      f"{len(partner_totals):>3d} partners  World={world:>15,.0f}  "
                      f"SG={sg:>13,.0f}  share={share:>6.2f}%")

                time.sleep(COMTRADE_DEP_INTER_CALL_SLEEP_SEC)

    # ── Coverage summary — show which (reporter × year) combinations are
    # complete vs partial vs missing across the 7 SITC codes. Done by
    # querying the DB rather than tracking in-memory, so it reflects
    # whatever's actually persisted (including prior runs).
    print("\n  --- Comtrade dep coverage (SITC partitions present per reporter × year) ---")
    print(f"    {'ISO':<4s} {'Reporter':<14s}  ", end="")
    for year in COMTRADE_DEP_YEARS:
        print(f"{year:>10s}", end="")
    print()
    print(f"    {'-'*4} {'-'*14}  {'-'*10*len(COMTRADE_DEP_YEARS)}")
    n_sitcs = len(COMTRADE_DEP_SITC_CODES)
    for iso2, (name, _) in COMTRADE_DEP_REPORTERS.items():
        print(f"    {iso2:<4s} {name:<14s}  ", end="")
        for year in COMTRADE_DEP_YEARS:
            period = f"{year}-12-31"
            r = conn.execute(
                "SELECT COUNT(DISTINCT sitc_code) AS n "
                "FROM trade_comtrade_dep WHERE period = ? AND reporter_iso2 = ?",
                (period, iso2),
            ).fetchone()
            n_present = r[0] if r else 0
            if n_present == n_sitcs:
                marker = f"{n_present}/{n_sitcs} ✓"
            elif n_present == 0:
                marker = f"{n_present}/{n_sitcs} ∅"
            else:
                marker = f"{n_present}/{n_sitcs} …"
            print(f"{marker:>10s}", end="")
        print()
    print(f"    Legend: ✓ all 7 SITC codes ingested | ∅ none yet (rerun later) | … partial")

    if empty_responses:
        print(f"\n  --- {len(empty_responses)} (reporter, year, SITC) combinations returned empty ---")
        print("    These will be retried on the next ingest run (no DB write yet).")
        # Group by year for quick scanning
        from collections import defaultdict
        by_year = defaultdict(list)
        for iso2, year, sitc in empty_responses:
            by_year[year].append(f"{iso2}/{sitc}")
        for year in sorted(by_year):
            joined = ", ".join(sorted(by_year[year]))
            print(f"    {year}: {joined}")

    return {
        "fetched_calls": fetched_calls,
        "skipped_calls": skipped_calls,
        "rows_written":  rows_written,
        "failures":      failures,
        "empty_responses": len(empty_responses),
    }


def fetch_singstat_merchandise() -> dict[str, pd.DataFrame]:
    """Fetch SingStat Table Builder rows for any source='singstat' entries.

    source_key format: "<tableId>:<seriesNo>" (e.g. "M451001:2.1.1").
    """
    import requests

    targets = {
        sid: sdef for sid, sdef in SERIES_REGISTRY.items() if sdef.get("source") == "singstat"
    }
    if not targets:
        return {}

    frames: dict[str, pd.DataFrame] = {}
    today = datetime.now(timezone.utc).date()
    earliest_year = today.year - SINGSTAT_YEARS_BACK
    guid_cache: dict[str, str] = {}

    for series_id, sdef in targets.items():
        source_key = str(sdef.get("source_key", ""))
        if ":" not in source_key:
            print(f"    SKIP   {series_id}: source_key must be '<tableId>:<seriesNo>'")
            continue
        table_id, series_no = source_key.split(":", 1)
        table_id = table_id.strip()
        series_no = series_no.strip()
        label = sdef.get("label", series_id)
        unit = sdef.get("unit", "")
        frequency = sdef.get("frequency", "Monthly")

        guid = _singstat_get_table_guid(table_id, guid_cache)
        if not guid:
            print(f"    FAIL   {series_id}: could not resolve GUID for {table_id}")
            continue

        url = SINGSTAT_ROW_URL.format(guid=guid, table_id=table_id, series_no=series_no)
        try:
            resp = requests.get(url, headers=SINGSTAT_HEADERS, timeout=30)
            if resp.status_code != 200:
                print(f"    FAIL   {series_id}: HTTP {resp.status_code} on {url}")
                continue
            payload = resp.json()
        except Exception as exc:
            print(f"    FAIL   {series_id}: {exc}")
            continue

        # Row data is a flat list of {"Key": "YYYY MMM", "Value": "<number>"}.
        if not isinstance(payload, list):
            print(f"    FAIL   {series_id}: unexpected payload shape {type(payload).__name__}")
            continue

        rows = []
        for entry in payload:
            key = str(entry.get("Key", "")).strip()
            raw_val = entry.get("Value")
            if not key or raw_val in (None, ""):
                continue
            try:
                value = float(str(raw_val).replace(",", ""))
            except (TypeError, ValueError):
                continue
            # Try monthly format first ("2025 Jan"), then quarterly ("2025 1Q")
            date = pd.to_datetime(key, format="%Y %b", errors="coerce")
            if pd.isna(date):
                # Quarterly: "2025 1Q" -> map to first month of quarter
                import re
                qm = re.match(r"(\d{4})\s+(\d)Q", key)
                if qm:
                    yr, q = int(qm.group(1)), int(qm.group(2))
                    month = (q - 1) * 3 + 1  # 1Q->Jan, 2Q->Apr, 3Q->Jul, 4Q->Oct
                    date = pd.Timestamp(year=yr, month=month, day=1)
            if pd.isna(date):
                continue
            if date.year < earliest_year:
                continue
            rows.append({"date": date, "value": value})

        if not rows:
            print(f"    EMPTY  {series_id}: no observations in window >= {earliest_year}")
            continue

        df = pd.DataFrame(rows).sort_values("date").reset_index(drop=True)
        df["series_id"] = series_id
        df["series_name"] = label
        df["source"] = "singstat"
        df["unit"] = unit
        df["frequency"] = frequency
        frames[series_id] = df
        print(f"    OK     {series_id:28s}  {len(df)} pts  ({df['date'].min().date()} -> {df['date'].max().date()})")

    return frames


# ---------------------------------------------------------------------------
# data.gov.sg ingestion (currently unused)
# ---------------------------------------------------------------------------
# We previously pulled the 4 IIP cluster series (petroleum, petrochemicals,
# chemicals_cluster, semiconductors) from data.gov.sg dataset
# d_ec1764482872e3a178f184464badd99e (a mirror of SingStat M355301, 2019=100
# base). SingStat rebased the IIP to 2025=100 and froze M355301 at Dec 2025,
# so we switched to fetching M355381 directly via the SingStat ingestor.
#
# If a future series ever needs to come from data.gov.sg, the ingestion
# pattern is two-step:
#   1. POST/GET https://api-open.data.gov.sg/v1/public/api/datasets/<id>/initiate-download
#      → returns { "data": { "url": "<presigned download URL>" } }
#      (with rate limiting via HTTP 429; back off and retry)
#   2. GET that URL → returns the CSV/XLSX file bytes.
# The dataset payload is whatever shape the dataset author published; for
# the wide-format IPI CSV we used to parse, the first column was 'DataSeries'
# and the remaining columns were 'YYYYMon' month labels.
#
# A general-purpose helper would take (dataset_id, target_series_keys) and
# return long-format frames; this dataset-specific implementation has been
# removed.


# ---------------------------------------------------------------------------
# Motorist.sg fuel price scraper
# ---------------------------------------------------------------------------

MOTORIST_TREND_URL = "https://www.motorist.sg/petrol-prices"
CHARTKICK_MARKER = 'new Chartkick["LineChart"]("chart-1", '

FUEL_GRADES = {
    "92": "RON 92",
    "95": "RON 95",
    "98": "RON 98",
    "premium": "Premium",
    "diesel": "Diesel",
}


def _unescape_js_string(value: str) -> str:
    return value.encode("utf-8").decode("unicode_escape")


def _extract_balanced_segment(text: str, start_char: str, end_char: str) -> str:
    start_index = text.find(start_char)
    if start_index == -1:
        raise RuntimeError("Unable to locate the start of the chart data segment.")
    depth = 0
    in_string = False
    string_char = ""
    escaped = False
    for index in range(start_index, len(text)):
        char = text[index]
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if in_string:
            if char == string_char:
                in_string = False
            continue
        if char in {"'", '"'}:
            in_string = True
            string_char = char
            continue
        if char == start_char:
            depth += 1
        elif char == end_char:
            depth -= 1
            if depth == 0:
                return text[start_index : index + 1]
    raise RuntimeError("Unable to locate the end of the chart data segment.")


def _extract_chartkick_series(response_text: str) -> list[dict]:
    import ast

    candidates = [response_text]
    try:
        unescaped = _unescape_js_string(response_text)
    except Exception:
        unescaped = response_text
    if unescaped != response_text:
        candidates.append(unescaped)

    for candidate in candidates:
        marker_index = candidate.find(CHARTKICK_MARKER)
        if marker_index == -1:
            continue
        chart_call_tail = candidate[marker_index + len(CHARTKICK_MARKER) :]
        series_literal = _extract_balanced_segment(chart_call_tail, "[", "]")
        try:
            return ast.literal_eval(series_literal)
        except Exception:
            try:
                return ast.literal_eval(_unescape_js_string(series_literal))
            except Exception:
                continue

    raise RuntimeError("Unable to locate fuel trend series data in the Motorist response.")


def fetch_motorist_fuel_prices() -> dict[str, pd.DataFrame]:
    """Scrape fuel price trends from Motorist.sg for all grades."""
    import time
    import requests

    frames: dict[str, pd.DataFrame] = {}

    for grade_key, grade_label in FUEL_GRADES.items():
        try:
            params = {
                "grade": grade_key,
                "date_range": "24",  # max 24 months
                "_": str(int(time.time() * 1000)),
            }
            headers = {
                "X-Requested-With": "XMLHttpRequest",
                "Accept": "text/javascript, */*; q=0.01",
                "Referer": MOTORIST_TREND_URL,
            }
            response = requests.get(MOTORIST_TREND_URL, params=params, headers=headers, timeout=20)
            response.raise_for_status()

            series = _extract_chartkick_series(response.text)

            rows: list[dict] = []
            for brand_series in series:
                brand_name = str(brand_series.get("name", "")).strip() or "Unknown"
                for date_label, value in brand_series.get("data", []):
                    rows.append({
                        "date": pd.to_datetime(date_label, format="%d %b %y", errors="coerce"),
                        "value": pd.to_numeric(value, errors="coerce"),
                        "series_name": f"{brand_name} ({grade_label})",
                        "unit": "SGD/Litre",
                        "frequency": "Daily",
                        "source": "motorist",
                    })

            df = pd.DataFrame(rows)
            if df.empty:
                print(f"    EMPTY  {grade_label}")
                continue

            df = df.dropna(subset=["date", "value"]).sort_values(["series_name", "date"]).reset_index(drop=True)

            series_id = f"motorist_{grade_key}"
            df["series_id"] = series_id
            frames[series_id] = df
            print(f"    OK     {grade_label:10s}  {len(df)} pts across {df['series_name'].nunique()} brands")

        except Exception as exc:
            print(f"    FAIL   {grade_label}: {exc}")

    return frames


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Middle East Monitor data pipeline — fetch + build + narratives.",
    )
    parser.add_argument(
        "--skip-narratives",
        action="store_true",
        help="Skip steps 11 and 12 (AI narrative generation and final rebuild). "
             "Useful for dev iteration where you don't want to spend $0.30-1.00 "
             "in API calls. The dashboard built in step 9 will still show "
             "whatever cached narratives were last generated.",
    )
    parser.add_argument(
        "--force-narratives",
        action="store_true",
        help="Force narrative regeneration even if no triggers have fired "
             "(bypasses the σ-based trigger gate). Useful for refreshing "
             "narratives after a prompt change.",
    )
    parser.add_argument(
        "--show-trigger-state",
        action="store_true",
        help="Run through fetchers + build + stats, then print the trigger "
             "evaluation and exit without spending on narratives. Useful for "
             "checking what would fire without committing API spend.",
    )
    parser.add_argument(
        "--skip-shipping-pipeline",
        action="store_true",
        help="Skip steps 7 + 8 (PortWatch download + nowcast compute). The "
             "existing shipping nowcast file (data/shipping/nowcast_results_s13.json) "
             "stays in place and gets re-projected into time_series. Useful for "
             "fast iteration on non-shipping work.",
    )
    parser.add_argument(
        "--force-shipping",
        action="store_true",
        help="Force the nowcast compute (step 8) even if the PortWatch "
             "download (step 7) brought no new data. Useful after a "
             "methodology change in the nowcast pipeline.",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("Middle East Monitor — Data Pipeline")
    print("=" * 60)

    # Ensure database exists
    init_db()
    conn = get_connection()

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # 1. CEIC
    print(f"\n[1/12] Fetching CEIC series...")
    ceic_frames = fetch_ceic_series()
    ceic_total = 0
    for series_id, df in ceic_frames.items():
        count = replace_series(series_id, df, conn)
        ceic_total += count
    conn.commit()
    upsert_metadata("ceic_last_updated", timestamp)
    print(f"  -> {len(ceic_frames)} series, {ceic_total} total rows written")

    # 1b. Derived series — recompute after CEIC fetch since they depend on it.
    # Currently just MAS Core Inflation MoM, derived from the level index.
    print(f"\n[1b] Computing derived series...")
    n_mom = compute_mas_core_mom(conn)
    print(f"  -> mas_core_inflation_mom: {n_mom} rows written")

    # 2. Google Sheets (Bloomberg price data)
    print(f"\n[2/12] Fetching Google Sheets (Bloomberg price data)...")
    gsheets_frames = fetch_google_sheets_series()
    gsheets_total = 0
    for series_id, df in gsheets_frames.items():
        count = replace_series(series_id, df, conn)
        gsheets_total += count
    conn.commit()
    upsert_metadata("google_sheets_last_updated", timestamp)
    print(f"  -> {len(gsheets_frames)} series, {gsheets_total} total rows written")

    # 3. SingStat trade (from the same Google Sheet — 3 trade tabs)
    print(f"\n[3/12] Fetching SingStat trade (Google Sheet)...")
    singstat_trade_df = fetch_singstat_trade_from_gsheets()
    singstat_trade_count = replace_singstat_trade(singstat_trade_df, conn)
    conn.commit()
    upsert_metadata("singstat_trade_last_updated", timestamp)
    print(f"  -> {singstat_trade_count} trade rows written to trade_singstat")

    # 3b. Project SingStat chemical exports → per-country time_series rows
    # (the 10 regional countries). Lets the chart_grid renderer consume them
    # without a new section type.
    print(f"\n[3b] Computing per-country chemical-export series from trade_singstat...")
    n_chem = compute_singstat_chem_export_country_series(conn)
    print(f"  -> {n_chem} rows written across 10 regional series_ids")
    print(f"\n[3b.b] Computing per-country refined-petroleum-export series (SITC 334)...")
    n_pet = compute_singstat_petroleum_export_country_series(conn)
    print(f"  -> {n_pet} rows written across 10 regional series_ids")

    # 3c. Singapore Trade tab derivations — annual ME shares of mineral fuel
    # imports per SITC, monthly aggregates, regional shares of chemical
    # exports, and monthly chemical export aggregates. Plus 2023-25
    # monthly-average benchmarks stashed in metadata for the chart reference
    # lines. Sourced entirely from trade_singstat (no API calls).
    print(f"\n[3c] Computing Singapore Trade tab derived series...")
    n_share_imp = compute_sg_me_import_shares(conn)
    n_mon_imp   = compute_sg_import_monthly_aggregates(conn)
    n_share_exp = compute_sg_chem_export_regional_shares(conn)
    n_mon_exp   = compute_sg_chem_export_monthly_aggregates(conn)
    print(f"  -> {n_share_imp} ME-share import rows | {n_mon_imp} monthly import-aggregate rows")
    print(f"  -> {n_share_exp} regional-share export rows | {n_mon_exp} monthly export-aggregate rows")

    # 3c.b Regional Trade tab — per-country MONTHLY LEVELS only.
    # The annual SHARES derivation depends on `trade_comtrade_dep` which
    # gets ingested by step [4b] further below — we re-run the shares
    # derivation AFTER [4b] so it picks up the freshly-ingested Comtrade
    # rows. The monthly levels come from `trade_singstat` (already
    # ingested above) and don't depend on Comtrade.
    print(f"\n[3c.b] Computing Regional Trade per-country monthly levels...")
    n_reg_lvl = compute_regional_chem_levels(conn)
    n_reg_fuel_lvl = compute_regional_fuel_levels(conn)
    print(f"  -> chemicals: {n_reg_lvl} rows | refined petroleum: {n_reg_fuel_lvl} rows")

    # 3d. (moved) Singapore shipping nowcast projection into time_series now
    # runs as part of step 8 — after the PortWatch download + nowcast compute
    # — so the projection always sees freshly-computed data instead of
    # whatever stale JSON was on disk.

    # 3e. Financial markets — yfinance (FX, US 10Y, COMEX commodities),
    # ADB AsianBondsOnline (ASEAN+VN sovereign 10Y yields), and
    # investing.com (LME/SHFE commodities, JKM LNG, CPO, etc.).
    # Replaces the older `scripts/markets/ingest_tier{1,2}.py` flow which
    # wrote to a separate `asean_markets.db` and required a follow-up sync.
    # Now writes directly to `iran_monitor.db`'s time_series.
    print(f"\n[3e/yfinance] Fetching FX / US 10Y / COMEX commodities (yfinance)...")
    n_yf = fetch_yfinance_financial_markets(conn, replace_series)
    conn.commit()
    upsert_metadata("yfinance_last_updated", timestamp)
    print(f"  -> {n_yf} yfinance rows written")

    # 3e.1 Derived FX index — rebase each currency to 100 at the reference
    # date so MYR (~4), JPY (~150), VND (~25k) can share one chart cleanly.
    print(f"\n[3e/fx-indexed] Computing rebased FX indices (base=100)...")
    n_fxi = compute_fx_indexed(conn)
    print(f"  -> {n_fxi} indexed FX rows written")

    # 3e.2 Derived rubber USc/kg — convert Bangkok STR 20 (THB/kg) to USc
    # using daily THB FX. Depends on both the CEIC rubber series (step 1)
    # and the yfinance THB series (step 3e/yfinance) — must run AFTER both.
    print(f"\n[3e/rubber-usc] Converting STR 20 rubber from THB/kg to USc/kg...")
    n_rub = compute_rubber_tsr20_usc(conn)
    print(f"  -> {n_rub} rubber-USc rows written")

    print(f"\n[3e/adb] Scraping ASEAN+VN 10Y bond yields (ADB AsianBondsOnline)...")
    n_adb = fetch_adb_bond_yields(conn)
    upsert_metadata("adb_bonds_last_updated", timestamp)
    print(f"  -> {n_adb} bond yield observations upserted (today)")

    print(f"\n[3e/investing] Scraping commodities (investing.com)...")
    n_inv = fetch_investing_commodities(conn)
    upsert_metadata("investing_last_updated", timestamp)
    print(f"  -> {n_inv} commodity observations upserted (today)")

    # 4. [DISABLED 2026-04-29] UN Comtrade monthly partner-level SG petroleum
    # trade — not currently surfaced anywhere on the dashboard (SingStat is
    # the authoritative SG trade view). Was costing ~30s + ~600 API calls per
    # pipeline run with no consumer. Re-enable by uncommenting if a future
    # chart needs the bilateral HS-coded SG petroleum trade detail.
    print(f"\n[4/12] UN Comtrade fetch — TEMPORARILY DISABLED (no current consumer; saves ~30s/run).")
    print(f"  Re-enable by uncommenting the block in update_data.py main(), step [4/12].")
    # trade_df = fetch_trade_from_comtrade()
    # trade_count = replace_trade(trade_df, conn)
    # conn.commit()
    # upsert_metadata("trade_last_updated", timestamp)
    # print(f"  -> {trade_count} trade rows written")

    # 4b. [PARKED 2026-04-29] UN Comtrade regional dependence ingest.
    #
    # Infrastructure is in place (schema, helpers, fetcher, retry/backoff,
    # resumable via only_stale, coverage matrix) but the step is disabled
    # because Comtrade SITC-Annual mode only had 2025 data for 3 of 10
    # reporters as of the parking date. See REGIONAL_TRADE_NOTES.md for
    # the full investigation log.
    # Re-enabled 2026-04-30 with 2025 dropped from COMTRADE_DEP_YEARS
    # (see REGIONAL_TRADE_NOTES.md §6 + the comments on the constant).

    print(f"\n[4b] Fetching Comtrade regional dependence (annual SITC × partner)...")
    only_stale = os.environ.get("COMTRADE_DEP_FULL_REFRESH", "0") != "1"
    if not only_stale:
        print("  COMTRADE_DEP_FULL_REFRESH=1 — clearing trade_comtrade_dep before refetch")
        conn.execute("DELETE FROM trade_comtrade_dep")
        conn.commit()
    counters = fetch_comtrade_regional_dep(conn, only_stale=only_stale)
    upsert_metadata("comtrade_dep_last_updated", timestamp)
    print(f"  -> calls fetched={counters['fetched_calls']}  skipped (already-present)="
          f"{counters['skipped_calls']}  rows written={counters['rows_written']}  "
          f"empty (will retry)={counters.get('empty_responses', 0)}  "
          f"failures={counters['failures']}")

    # 4c. Now that Comtrade dependence rows are in `trade_comtrade_dep`,
    # compute the per-country annual share-from-SG series for the Regional
    # Trade tab cards. Has to run AFTER [4b] so it picks up the freshly-
    # ingested Comtrade data.
    print(f"\n[4c] Computing Regional Trade annual SG-share series...")
    n_reg_share = compute_regional_chem_share_from_sg(conn)
    n_reg_fuel_share = compute_regional_fuel_share_from_sg(conn)
    print(f"  -> chemicals: {n_reg_share} rows | refined petroleum: {n_reg_fuel_share} rows")

    # 5. SingStat Table Builder (petroleum trade + construction + WTI + electricity)
    print(f"\n[5/12] Fetching SingStat Table Builder series...")
    singstat_frames = fetch_singstat_merchandise()
    singstat_total = 0
    for series_id, df in singstat_frames.items():
        count = replace_series(series_id, df, conn)
        singstat_total += count
    conn.commit()
    upsert_metadata("singstat_last_updated", timestamp)
    print(f"  -> {len(singstat_frames)} series, {singstat_total} total rows written")

    # 6. data.gov.sg — placeholder freshness key (the IIP series now flow
    # through the SingStat ingestor in step 5 via M355381).
    upsert_metadata("ipi_last_updated", timestamp)

    # 7. Motorist fuel prices
    print(f"\n[6/12] Fetching Motorist.sg fuel prices...")
    motorist_frames = fetch_motorist_fuel_prices()
    motorist_total = 0
    for series_id, df in motorist_frames.items():
        count = replace_series(series_id, df, conn)
        motorist_total += count
    conn.commit()
    upsert_metadata("motorist_last_updated", timestamp)
    print(f"  -> {len(motorist_frames)} grades, {motorist_total} total rows written")

    # ─────────────────────────────────────────────────────────────────────
    # Steps 7-8: Shipping nowcast pipeline (fully self-contained)
    # ─────────────────────────────────────────────────────────────────────

    # 7. PortWatch download — incremental update from IMF's public ArcGIS
    # API. Cheap on most days (no new data) since PortWatch publishes
    # weekly on Tuesday EST.
    portwatch_csv = PROJECT_ROOT / "data" / "portwatch" / "Daily_Ports_Data.csv"
    if args.skip_shipping_pipeline:
        print(f"\n[7/12] PortWatch download — SKIPPED (--skip-shipping-pipeline).")
        portwatch_changed = False
    else:
        prev_max_date = _csv_max_date(portwatch_csv)
        print(f"\n[7/12] Downloading latest PortWatch data (incremental)...")
        if prev_max_date:
            print(f"  Existing CSV max date: {prev_max_date}")
        _run_subprocess(
            [sys.executable, str(PROJECT_ROOT / "scripts" / "shipping" / "download_portwatch_data.py")],
            label="download_portwatch_data.py", hard_fail=False,
        )
        new_max_date = _csv_max_date(portwatch_csv)
        if new_max_date:
            print(f"  Post-download CSV max date: {new_max_date}")
        portwatch_changed = (new_max_date != prev_max_date) and new_max_date is not None

    # 8. Shipping nowcast — STL + Ridge regression on the PortWatch data.
    # Skipped if step 7 brought no new rows, unless --force-shipping. After
    # the nowcast JSON is fresh (or unchanged), project it into time_series
    # so the Singapore Shipping tab renders against current data.
    if args.skip_shipping_pipeline:
        print(f"\n[8/12] Shipping nowcast — SKIPPED (--skip-shipping-pipeline).")
        print(f"  Re-projecting existing nowcast JSON into time_series...")
        n_nowcast = compute_singapore_shipping_nowcast(conn)
        print(f"  -> {n_nowcast} nowcast rows written")
    elif portwatch_changed or args.force_shipping:
        reason = "PortWatch brought new data" if portwatch_changed else "--force-shipping set"
        print(f"\n[8/12] Computing shipping nowcast (STL + Ridge); reason: {reason}...")
        _run_subprocess(
            [sys.executable, str(PROJECT_ROOT / "scripts" / "shipping" / "nowcast_pipeline.py")],
            label="nowcast_pipeline.py", hard_fail=False,
        )
        print(f"  Projecting fresh nowcast JSON into time_series...")
        n_nowcast = compute_singapore_shipping_nowcast(conn)
        print(f"  -> {n_nowcast} nowcast rows written")
    else:
        print(f"\n[8/12] Shipping nowcast — SKIPPED (PortWatch data unchanged; "
              f"PortWatch publishes weekly on Tuesday EST).")
        print(f"  Re-projecting existing nowcast JSON into time_series...")
        n_nowcast = compute_singapore_shipping_nowcast(conn)
        print(f"  -> {n_nowcast} nowcast rows written")

    # Done with data fetching
    upsert_metadata("last_full_update", timestamp)
    conn.close()

    # ─────────────────────────────────────────────────────────────────────
    # Steps 9-12: Build → stats → narratives → rebuild
    # ─────────────────────────────────────────────────────────────────────

    # 9. Build the dashboard once. This emits data/chart_manifest.json which
    # the summary-stats step depends on. The rendered HTML at this point
    # carries whatever AI narratives are currently in the DB metadata
    # table (i.e. last run's narratives, or none on first run).
    print(f"\n[9/12] Building dashboard (1st pass — emits chart manifest)...")
    _run_subprocess([sys.executable, str(PROJECT_ROOT / "scripts" / "build_iran_monitor.py")],
                    label="build_iran_monitor.py", hard_fail=True)

    # 10. Compute summary statistics. Reads chart_manifest.json + queries the
    # DB to produce data/summary_stats.json — the input to step 11.
    print(f"\n[10/12] Computing summary statistics...")
    _run_subprocess([sys.executable, str(PROJECT_ROOT / "scripts" / "compute_summary_stats.py")],
                    label="compute_summary_stats.py", hard_fail=True)

    # 10b. Evaluate narrative triggers — decide whether to refresh AI
    # narratives this run. Avoids burning $0.30-1.00 on every refresh
    # when nothing material has moved. Honoured unless --force-narratives.
    trigger_decision = None
    if not args.skip_narratives:
        trigger_decision = _evaluate_narrative_triggers(forced=args.force_narratives)

    if args.show_trigger_state:
        print(f"\n[11/12] --show-trigger-state set — exiting without running narratives.")
        return

    if args.skip_narratives:
        print(f"\n[11/12] Generating AI narratives — SKIPPED (--skip-narratives flag set).")
        print(f"\n[12/12] Rebuild dashboard with narratives — SKIPPED (no fresh narratives).")
        print(f"  The dashboard built in step 9 still reflects whatever cached narratives")
        print(f"  were in the DB. Re-run without --skip-narratives to refresh them.")
    elif trigger_decision is not None and not trigger_decision.refresh:
        print(f"\n[11/12] Generating AI narratives — SKIPPED (no triggers fired).")
        print(f"\n[12/12] Rebuild dashboard with narratives — SKIPPED (no fresh narratives).")
        print(f"  The dashboard built in step 9 still reflects the cached narratives.")
        print(f"  Use --force-narratives to override the trigger gate.")
    else:
        # 11. Generate AI narratives. 4 Sonnet 4.6 calls (~$0.30-1.00, 30-90s).
        # Treat failures as warnings — the dashboard from step 9 still shows
        # cached narratives, so a single failed refresh isn't catastrophic.
        print(f"\n[11/12] Generating AI narratives (4 Sonnet 4.6 calls)...")
        narratives_ok = _run_subprocess(
            [sys.executable, str(PROJECT_ROOT / "scripts" / "generate_narratives.py")],
            label="generate_narratives.py", hard_fail=False,
        )

        # 12. Rebuild the dashboard so the freshly-generated narratives get
        # embedded into the HTML. Skip if step 11 failed (nothing new to embed).
        if narratives_ok:
            print(f"\n[12/12] Rebuilding dashboard with fresh narratives...")
            _run_subprocess([sys.executable, str(PROJECT_ROOT / "scripts" / "build_iran_monitor.py")],
                            label="build_iran_monitor.py (2nd pass)", hard_fail=True)
        else:
            print(f"\n[12/12] Rebuild SKIPPED — narrative generation failed in step 11.")
            print(f"  The dashboard from step 9 still shows cached narratives.")

    db_size = DB_PATH.stat().st_size / 1024
    print(f"\n{'=' * 60}")
    print(f"Done. Database: {DB_PATH} ({db_size:.0f} KB)")
    print(f"Timestamp: {timestamp}")
    print(f"{'=' * 60}")


# ---------------------------------------------------------------------------
# Narrative trigger evaluation
# ---------------------------------------------------------------------------
def _evaluate_narrative_triggers(*, forced: bool):
    """Evaluate σ-based narrative triggers and print the decision.
    Returns the TriggerDecision (with `.refresh` attr) or a forced-True
    sentinel object if --force-narratives. Returns None if the trigger
    config is missing (treats as 'always refresh' for backward
    compatibility — print a warning so the user notices)."""
    print(f"\n[10b/12] Evaluating narrative triggers...")

    if forced:
        print(f"  --force-narratives set — bypassing trigger gate.")
        class _Forced:
            refresh = True
            reasons = ["--force-narratives flag bypasses the trigger gate."]
        return _Forced()

    try:
        from src.narrative_triggers_v2 import (   # noqa: E402
            evaluate_triggers, load_thresholds, load_snapshot,
        )
    except ImportError as e:
        print(f"  ⚠️  Could not import trigger module ({e}); will refresh narratives.")
        return None

    try:
        thresholds = load_thresholds()
    except FileNotFoundError as e:
        print(f"  ⚠️  {e}")
        print(f"  Defaulting to refresh (no thresholds means we can't gate).")
        return None

    stats_path = PROJECT_ROOT / "data" / "summary_stats.json"
    if not stats_path.exists():
        print(f"  ⚠️  summary_stats.json missing; will refresh narratives.")
        return None
    current_stats = json.loads(stats_path.read_text(encoding="utf-8"))

    conn = get_connection()
    try:
        last_snapshot = load_snapshot(conn)
    finally:
        conn.close()

    decision = evaluate_triggers(current_stats, last_snapshot, thresholds)

    print(f"  Last narrative: {'never' if decision.age_days is None else f'{decision.age_days:.1f} days ago'}")
    print(f"  Trigger series checked: {decision.n_series_checked}")
    print(f"  Triggers fired: {decision.n_series_fired}")
    print(f"  Decision: {'REFRESH' if decision.refresh else 'SKIP'}")
    if decision.reasons:
        for r in decision.reasons[:8]:
            print(f"    - {r}")
        if len(decision.reasons) > 8:
            print(f"    ... and {len(decision.reasons) - 8} more reasons.")
    return decision


# ---------------------------------------------------------------------------
# Shipping pipeline helper
# ---------------------------------------------------------------------------
def _csv_max_date(csv_path: Path, date_col: str = "date") -> str | None:
    """Return the max value in `date_col` across the CSV, or None if the
    file doesn't exist or the column is missing. Used to detect whether
    an incremental PortWatch download brought new rows."""
    if not csv_path.exists():
        return None
    try:
        import csv as _csv
        max_date = ""
        with csv_path.open("r", encoding="utf-8-sig") as f:
            reader = _csv.DictReader(f)
            if not reader.fieldnames:
                return None
            # Look for the date column (case-insensitive, common variants).
            col = None
            for candidate in (date_col, "Date", "DATE", "date_str", "obs_date"):
                if candidate in reader.fieldnames:
                    col = candidate
                    break
            if col is None:
                # Fall back to first column.
                col = reader.fieldnames[0]
            for row in reader:
                v = (row.get(col) or "").strip()
                if v and v > max_date:
                    max_date = v
        return max_date or None
    except Exception:
        # Best-effort — caller treats None as "couldn't read", which forces
        # a nowcast recompute (safe default).
        return None


# ---------------------------------------------------------------------------
# Subprocess helper
# ---------------------------------------------------------------------------
def _run_subprocess(cmd: list[str], *, label: str, hard_fail: bool) -> bool:
    """Run a subprocess and stream its output live. Returns True on success.

    If `hard_fail` is True, a non-zero exit code raises CalledProcessError
    and aborts the pipeline. If False, prints a warning and returns False
    so the caller can decide whether to continue.
    """
    try:
        subprocess.run(cmd, check=True, cwd=PROJECT_ROOT)
        return True
    except subprocess.CalledProcessError as exc:
        msg = f"  ⚠️  {label} exited with code {exc.returncode}"
        if hard_fail:
            print(msg)
            raise
        print(f"{msg} — continuing (this step is non-blocking).")
        return False
    except FileNotFoundError as exc:
        msg = f"  ⚠️  {label} script not found: {exc.filename}"
        if hard_fail:
            print(msg)
            raise
        print(f"{msg} — continuing.")
        return False


if __name__ == "__main__":
    main()
