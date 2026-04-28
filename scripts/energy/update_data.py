"""
Data pipeline: fetches from CEIC, Google Sheets, UN Comtrade, SingStat, and
Motorist.sg, then writes everything into the SQLite database.

Run this from your MAS network (where CEIC is accessible).

Usage:
    1. Fill in .env with credentials (see .env.example)
    2. pip install -r requirements-pipeline.txt
    3. python scripts/update_data.py

Sources:
    - CEIC API        -> macro indicators (crude oil, transport, financial)
    - Google Sheets   -> Bloomberg terminal data (commodity spot prices)
    - UN Comtrade API -> monthly partner-level trade (crude, products, petchem)
    - SingStat API    -> monthly petroleum import/export totals (M451001)
    - Motorist.sg     -> daily retail fuel prices by brand
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
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
    get_connection,
    get_metadata,
    init_db,
    replace_series,
    replace_trade,
    upsert_metadata,
)
from src.series_config import SERIES_REGISTRY

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


load_env(PROJECT_ROOT / ".env")


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

SHEET_TABS = ("Daily", "Weekly", "Monthly")
HEADER_ROW_INDEX = 0
NAME_ROW_INDEX = 1
UNIT_ROW_INDEX = 2
DATA_START_ROW_INDEX = 4


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
    if len(rows) <= DATA_START_ROW_INDEX:
        return pd.DataFrame()

    padded = _pad_rows(rows)
    header_row = padded[HEADER_ROW_INDEX]
    name_row = padded[NAME_ROW_INDEX]
    unit_row = padded[UNIT_ROW_INDEX]

    records: list[dict[str, Any]] = []
    for col_idx in range(1, len(header_row)):
        ticker = str(header_row[col_idx]).strip()
        series_name = str(name_row[col_idx]).strip() or ticker or f"{sheet_name} Series {col_idx}"
        unit = str(unit_row[col_idx]).strip()

        if not any([ticker, series_name, unit]):
            continue

        for row in padded[DATA_START_ROW_INDEX:]:
            raw_date = str(row[0]).strip()
            raw_value = str(row[col_idx]).strip() if col_idx < len(row) else ""
            if not raw_date or not raw_value:
                continue
            records.append({
                "date": raw_date,
                "value": raw_value,
                "series_name": series_name,
                "unit": unit,
                "frequency": sheet_name,
            })

    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records)
    df["date"] = pd.to_datetime(df["date"], errors="coerce", dayfirst=True)
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


def fetch_google_sheets_series() -> dict[str, pd.DataFrame]:
    """Fetch Bloomberg-sourced commodity price data from Google Sheets."""
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

    for tab_name in SHEET_TABS:
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

            # Create one entry per unique series in this tab
            for series_name in df["series_name"].unique():
                series_df = df[df["series_name"] == series_name].copy()
                # Use a sanitized series_id based on source and name
                series_id = f"gsheets_{tab_name.lower()}_{series_name[:50]}"
                series_df["series_id"] = series_id
                series_df["source"] = "google_sheets"
                frames[series_id] = series_df
                print(f"    OK     {tab_name:8s}  {series_name:50s}  {len(series_df)} pts")

        except Exception as exc:
            print(f"    FAIL   {tab_name} tab: {exc}")

    # Apply unit conversions for series stored in non-standard units
    frames = _apply_gsheets_unit_conversions(frames)

    return frames


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
    print("=" * 60)
    print("Energy Dashboard — Data Pipeline")
    print("=" * 60)

    # Ensure database exists
    init_db()
    conn = get_connection()

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # 1. CEIC
    print(f"\n[1/5] Fetching CEIC series...")
    ceic_frames = fetch_ceic_series()
    ceic_total = 0
    for series_id, df in ceic_frames.items():
        count = replace_series(series_id, df, conn)
        ceic_total += count
    conn.commit()
    upsert_metadata("ceic_last_updated", timestamp)
    print(f"  -> {len(ceic_frames)} series, {ceic_total} total rows written")

    # 2. Google Sheets (Bloomberg data)
    print(f"\n[2/5] Fetching Google Sheets (Bloomberg data)...")
    gsheets_frames = fetch_google_sheets_series()
    gsheets_total = 0
    for series_id, df in gsheets_frames.items():
        count = replace_series(series_id, df, conn)
        gsheets_total += count
    conn.commit()
    upsert_metadata("google_sheets_last_updated", timestamp)
    print(f"  -> {len(gsheets_frames)} series, {gsheets_total} total rows written")

    # 3. UN Comtrade (monthly, partner-level)
    print(f"\n[3/5] Fetching UN Comtrade (monthly partner-level trade)...")
    trade_df = fetch_trade_from_comtrade()
    trade_count = replace_trade(trade_df, conn)
    conn.commit()
    upsert_metadata("trade_last_updated", timestamp)
    print(f"  -> {trade_count} trade rows written")

    # 4. SingStat Table Builder (petroleum trade + construction + WTI + electricity)
    print(f"\n[4/6] Fetching SingStat Table Builder series...")
    singstat_frames = fetch_singstat_merchandise()
    singstat_total = 0
    for series_id, df in singstat_frames.items():
        count = replace_series(series_id, df, conn)
        singstat_total += count
    conn.commit()
    upsert_metadata("singstat_last_updated", timestamp)
    print(f"  -> {len(singstat_frames)} series, {singstat_total} total rows written")

    # 5. data.gov.sg — Industrial Production Index sub-indices
    # NB: step 5 was previously a data.gov.sg IPI fetch. The IIP series now
    # flow through the SingStat ingestor in step 4 (M355381). The freshness
    # metadata key is kept in case downstream consumers reference it.
    upsert_metadata("ipi_last_updated", timestamp)

    # 6. Motorist fuel prices
    print(f"\n[6/6] Fetching Motorist.sg fuel prices...")
    motorist_frames = fetch_motorist_fuel_prices()
    motorist_total = 0
    for series_id, df in motorist_frames.items():
        count = replace_series(series_id, df, conn)
        motorist_total += count
    conn.commit()
    upsert_metadata("motorist_last_updated", timestamp)
    print(f"  -> {len(motorist_frames)} grades, {motorist_total} total rows written")

    # Done with data fetching
    upsert_metadata("last_full_update", timestamp)
    conn.close()

    # 7. LLM narrative (conditional on triggers)
    print(f"\n[7/7] Checking narrative triggers...")
    try:
        _maybe_regenerate_narrative()
    except Exception as exc:
        print(f"  SKIP: Narrative generation failed: {exc}")

    db_size = DB_PATH.stat().st_size / 1024
    print(f"\n{'=' * 60}")
    print(f"Done. Database: {DB_PATH} ({db_size:.0f} KB)")
    print(f"Timestamp: {timestamp}")
    print(f"{'=' * 60}")


# ---------------------------------------------------------------------------
# LLM narrative generation
# ---------------------------------------------------------------------------

from src.narrative_prompt import NARRATIVE_PROMPT


def _maybe_regenerate_narrative():
    """Check triggers and regenerate the LLM narrative if needed."""
    # Import here to avoid circular deps and to keep the pipeline runnable
    # even without anthropic installed (it just skips narrative)
    sys.path.insert(0, str(PROJECT_ROOT))
    from build_dashboard import export_time_series, compute_summary
    from src.narrative_triggers import evaluate_triggers

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        print("  SKIP: ANTHROPIC_API_KEY not set")
        return

    # Compute current stats
    series_data = export_time_series()
    current_stats = compute_summary(series_data)

    # Load previous stats and timestamp
    prev_stats_json = get_metadata("narrative_prev_stats")
    prev_timestamp = get_metadata("narrative_generated_at")
    prev_stats = json.loads(prev_stats_json) if prev_stats_json else None

    # Evaluate triggers
    fired = evaluate_triggers(current_stats, prev_stats, prev_timestamp)

    if not fired:
        print("  No triggers fired — keeping cached narrative")
        return

    print(f"  {len(fired)} trigger(s) fired:")
    for t in fired:
        print(f"    - {t.id}: {t.description}")

    # Call Claude API
    print("  Generating narrative via Claude API...")
    try:
        import anthropic
    except ImportError:
        print("  SKIP: 'anthropic' package not installed (pip install anthropic)")
        return

    client = anthropic.Anthropic(api_key=api_key)
    stats_json = json.dumps(current_stats, indent=2)
    prompt = NARRATIVE_PROMPT.format(stats_json=stats_json)

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )

    narrative = message.content[0].text.strip()
    print(f"  Generated {len(narrative)} chars")

    # Store narrative + stats + timestamp
    gen_timestamp = datetime.now(timezone.utc).isoformat()
    upsert_metadata("llm_narrative", narrative)
    upsert_metadata("narrative_prev_stats", json.dumps(current_stats))
    upsert_metadata("narrative_generated_at", gen_timestamp)
    upsert_metadata("narrative_triggers_fired", ", ".join(t.id for t in fired))

    print(f"  Narrative stored (generated at {gen_timestamp})")


if __name__ == "__main__":
    main()
