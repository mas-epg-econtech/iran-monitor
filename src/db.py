"""SQLite database helper for Iran Monitor.

Wraps the unified iran_monitor.db which holds time-series indicators from all
sources (CEIC, Google Sheets, Motorist, SingStat, DataGov, yfinance, ADB,
Investing.com), plus trade data, indicator metadata, data source attribution,
and ingestion logs.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "iran_monitor.db"


def get_connection(db_path: Path | str | None = None) -> sqlite3.Connection:
    path = str(db_path or DB_PATH)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Path | str | None = None) -> None:
    """Create tables if they don't exist."""
    conn = get_connection(db_path)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS time_series (
            date        TEXT    NOT NULL,
            value       REAL    NOT NULL,
            series_id   TEXT    NOT NULL,
            series_name TEXT    NOT NULL,
            source      TEXT    NOT NULL,
            unit        TEXT    NOT NULL DEFAULT '',
            frequency   TEXT    NOT NULL DEFAULT ''
        );

        CREATE INDEX IF NOT EXISTS idx_ts_series_id ON time_series (series_id);
        CREATE INDEX IF NOT EXISTS idx_ts_source    ON time_series (source);

        CREATE TABLE IF NOT EXISTS trade (
            period          TEXT    NOT NULL,   -- "YYYY-MM"
            year            INTEGER NOT NULL,
            month           INTEGER NOT NULL,
            nomenclature    TEXT,
            reporter_iso3   TEXT,
            product_code    TEXT    NOT NULL,
            reporter_name   TEXT,
            partner_name    TEXT    NOT NULL,
            partner_iso3    TEXT,
            trade_flow_name TEXT    NOT NULL,
            trade_flow_code INTEGER,
            trade_value     REAL    NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_trade_period  ON trade (period);
        CREATE INDEX IF NOT EXISTS idx_trade_product ON trade (product_code);
        CREATE INDEX IF NOT EXISTS idx_trade_year    ON trade (year);

        CREATE TABLE IF NOT EXISTS metadata (
            key   TEXT PRIMARY KEY,
            value TEXT
        );
        """
    )
    conn.commit()
    conn.close()


def upsert_metadata(key: str, value: str, db_path: Path | str | None = None) -> None:
    conn = get_connection(db_path)
    conn.execute(
        "INSERT INTO metadata (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    conn.commit()
    conn.close()


def get_metadata(key: str, default: str = "", db_path: Path | str | None = None) -> str:
    conn = get_connection(db_path)
    row = conn.execute("SELECT value FROM metadata WHERE key = ?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else default


def load_time_series(series_ids: list[str], db_path: Path | str | None = None) -> pd.DataFrame:
    """Load time series data for the given series IDs."""
    if not series_ids:
        return pd.DataFrame()

    conn = get_connection(db_path)
    placeholders = ",".join("?" for _ in series_ids)
    query = f"""
        SELECT date, value, series_id, series_name, source, unit, frequency
        FROM time_series
        WHERE series_id IN ({placeholders})
        ORDER BY series_name, date
    """
    df = pd.read_sql_query(query, conn, params=series_ids)
    conn.close()

    if not df.empty:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
        df = df.dropna(subset=["date", "value"])

    return df


def load_time_series_by_name(series_names: list[str], db_path: Path | str | None = None) -> pd.DataFrame:
    """Load time series data matching exact series names."""
    if not series_names:
        return pd.DataFrame()

    conn = get_connection(db_path)
    placeholders = ",".join("?" for _ in series_names)
    query = f"""
        SELECT date, value, series_id, series_name, source, unit, frequency
        FROM time_series
        WHERE LOWER(TRIM(series_name)) IN ({placeholders})
        ORDER BY series_name, date
    """
    params = [name.strip().lower() for name in series_names]
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()

    if not df.empty:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
        df = df.dropna(subset=["date", "value"])

    return df


def load_trade_data(db_path: Path | str | None = None) -> pd.DataFrame:
    """Load all trade data (monthly rows).

    Returns columns: Period (YYYY-MM), Year, Month, Nomenclature, ReporterISO3,
    ProductCode, ReporterName, PartnerName, PartnerISO3, TradeFlowName,
    TradeFlowCode, and TradeValue in 1000 USD.
    """
    conn = get_connection(db_path)
    df = pd.read_sql_query(
        """
        SELECT period AS Period,
               year AS Year,
               month AS Month,
               nomenclature AS Nomenclature,
               reporter_iso3 AS ReporterISO3,
               product_code AS ProductCode,
               reporter_name AS ReporterName,
               partner_name AS PartnerName,
               partner_iso3 AS PartnerISO3,
               trade_flow_name AS TradeFlowName,
               trade_flow_code AS TradeFlowCode,
               trade_value AS "TradeValue in 1000 USD"
        FROM trade
        ORDER BY product_code, period, partner_name
        """,
        conn,
    )
    conn.close()

    if not df.empty:
        df["Year"] = pd.to_numeric(df["Year"], errors="coerce").astype("Int64")
        df["Month"] = pd.to_numeric(df["Month"], errors="coerce").astype("Int64")
        df["TradeValue in 1000 USD"] = pd.to_numeric(df["TradeValue in 1000 USD"], errors="coerce")
        for col in ["Period", "ProductCode", "TradeFlowName", "PartnerName", "PartnerISO3"]:
            df[col] = df[col].astype(str).str.strip()

    return df


def load_motorist_fuel_prices(grade: str, db_path: Path | str | None = None) -> pd.DataFrame:
    """Load Motorist fuel price data for a specific grade."""
    conn = get_connection(db_path)
    series_id = f"motorist_{grade}"
    df = pd.read_sql_query(
        """
        SELECT date, value, series_id, series_name, source, unit, frequency
        FROM time_series
        WHERE series_id = ?
        ORDER BY series_name, date
        """,
        conn,
        params=[series_id],
    )
    conn.close()

    if not df.empty:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
        df = df.dropna(subset=["date", "value"])

    return df


def replace_series(series_id: str, df: pd.DataFrame, conn: sqlite3.Connection) -> int:
    """Delete existing rows for a series and insert new ones. Returns row count."""
    conn.execute("DELETE FROM time_series WHERE series_id = ?", (series_id,))
    if df.empty:
        return 0
    # SQLite doesn't natively bind pandas Timestamps — cast the date column to ISO strings.
    out = df[["date", "value", "series_id", "series_name", "source", "unit", "frequency"]].copy()
    out["date"] = pd.to_datetime(out["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    rows = out.values.tolist()
    conn.executemany(
        "INSERT INTO time_series (date, value, series_id, series_name, source, unit, frequency) VALUES (?,?,?,?,?,?,?)",
        rows,
    )
    return len(rows)


def replace_trade(df: pd.DataFrame, conn: sqlite3.Connection) -> int:
    """Replace all trade data. Returns row count.

    Expects columns: period, year, month, nomenclature, reporter_iso3,
    product_code, reporter_name, partner_name, partner_iso3,
    trade_flow_name, trade_flow_code, trade_value.
    """
    conn.execute("DELETE FROM trade")
    if df.empty:
        return 0
    rows = df[
        ["period", "year", "month", "nomenclature", "reporter_iso3",
         "product_code", "reporter_name", "partner_name", "partner_iso3",
         "trade_flow_name", "trade_flow_code", "trade_value"]
    ].values.tolist()
    conn.executemany(
        "INSERT INTO trade (period, year, month, nomenclature, reporter_iso3, "
        "product_code, reporter_name, partner_name, partner_iso3, "
        "trade_flow_name, trade_flow_code, trade_value) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        rows,
    )
    return len(rows)
