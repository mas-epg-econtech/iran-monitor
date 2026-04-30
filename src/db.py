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

        -- SingStat trade data, sourced from the colleagues' Google Sheet
        -- ('dashboard data v2'). Lives separate from the Comtrade `trade`
        -- table because: different currency (SGD vs USD), different code
        -- system (SITC vs HS), and the dashboard treats SingStat as the
        -- authoritative SG view (Comtrade is backup that probably won't be
        -- surfaced in the UI).
        CREATE TABLE IF NOT EXISTS trade_singstat (
            period          TEXT    NOT NULL,   -- "YYYY-MM-DD"
            frequency       TEXT    NOT NULL,   -- "Annual" or "Monthly"
            flow            TEXT    NOT NULL,   -- "Imports" or "Exports"
            product_code    TEXT    NOT NULL,   -- e.g. "SITC_3", "SITC_333", "Chemicals_DX"
            product_label   TEXT,                -- friendly e.g. "Mineral Fuels"
            partner_name    TEXT    NOT NULL,    -- raw SingStat label, e.g. "KOREA, REP OF"
            partner_iso2    TEXT,                -- e.g. "KR" — NULL if unmapped
            partner_display TEXT,                -- friendly e.g. "South Korea" — NULL if unmapped
            value_sgd_thou  REAL    NOT NULL,    -- SGD thousands, raw from sheet
            PRIMARY KEY (period, frequency, flow, product_code, partner_name)
        );

        CREATE INDEX IF NOT EXISTS idx_singstat_partner ON trade_singstat (partner_name);
        CREATE INDEX IF NOT EXISTS idx_singstat_product ON trade_singstat (product_code);

        -- Comtrade partner-level trade for the 10 regional countries — used
        -- to compute exposure ratios (e.g., "Malaysia's ME share of mineral
        -- fuel imports", "Indonesia's SG share of chemical imports").
        --
        -- One row per (reporter, partner, sitc_code, period). Values in USD
        -- (Comtrade's native currency). Partner uses Comtrade's ISO3 with
        -- the special code "W00" representing the World aggregate row that
        -- supplies the denominator for share calculations.
        --
        -- Schema is generic enough to support any SITC code we add later;
        -- the renderer's section config decides which codes / partners to
        -- surface per chart.
        CREATE TABLE IF NOT EXISTS trade_comtrade_dep (
            period          TEXT    NOT NULL,   -- "YYYY-12-31" for annual
            reporter_iso2   TEXT    NOT NULL,   -- our 10 regional countries
            partner_iso3    TEXT    NOT NULL,   -- Comtrade ISO3, "W00" = World
            partner_name    TEXT    NOT NULL,   -- partnerDesc from Comtrade
            sitc_code       TEXT    NOT NULL,   -- '5','51','54','3','333','334','343'
            value_usd       REAL    NOT NULL,   -- primaryValue from Comtrade
            PRIMARY KEY (period, reporter_iso2, partner_iso3, sitc_code)
        );

        CREATE INDEX IF NOT EXISTS idx_comdep_reporter ON trade_comtrade_dep (reporter_iso2);
        CREATE INDEX IF NOT EXISTS idx_comdep_partner  ON trade_comtrade_dep (partner_iso3);
        CREATE INDEX IF NOT EXISTS idx_comdep_sitc     ON trade_comtrade_dep (sitc_code);

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
    """Delete existing rows for a series and insert new ones. Returns row count.

    The time_series table has PRIMARY KEY (date, series_id). Some upstream
    fetchers (notably Motorist, which scrapes one row per pump-station brand
    per day all under series_id 'motorist_<grade>') produce multiple input
    rows sharing the same (date, series_id) — those have to be collapsed
    before insert or SQLite raises a UNIQUE constraint error.

    Strategy: aggregate duplicates by averaging `value` (yields a meaningful
    daily-average across whatever brands were scraped) and taking the first
    non-null metadata. This is deterministic and stable across reruns; it's
    also more useful than the alternative INSERT-OR-REPLACE behaviour where
    one brand "wins" non-deterministically.
    """
    conn.execute("DELETE FROM time_series WHERE series_id = ?", (series_id,))
    if df.empty:
        return 0
    # SQLite doesn't natively bind pandas Timestamps — cast the date column to ISO strings.
    out = df[["date", "value", "series_id", "series_name", "source", "unit", "frequency"]].copy()
    out["date"] = pd.to_datetime(out["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    out = out.dropna(subset=["date", "value"])
    if out.empty:
        return 0
    # Collapse (date, series_id) duplicates: mean of value, first of metadata.
    if out.duplicated(subset=["date", "series_id"]).any():
        out = (
            out.groupby(["date", "series_id"], as_index=False)
               .agg({
                   "value":       "mean",
                   "series_name": "first",
                   "source":      "first",
                   "unit":        "first",
                   "frequency":   "first",
               })
        )
    rows = out[["date", "value", "series_id", "series_name", "source", "unit", "frequency"]].values.tolist()
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


def upsert_comtrade_dep_partition(
    conn: sqlite3.Connection,
    period: str,
    reporter_iso2: str,
    sitc_code: str,
    rows: list[tuple[str, str, float]],
) -> int:
    """Replace one (period, reporter, sitc) partition of trade_comtrade_dep.

    `rows` is a list of (partner_iso3, partner_name, value_usd) — typically
    one entry per partner returned by a single Comtrade call. The whole
    partition is wiped and rewritten so partial reruns are idempotent.

    Returns the number of rows written.
    """
    conn.execute(
        "DELETE FROM trade_comtrade_dep "
        "WHERE period = ? AND reporter_iso2 = ? AND sitc_code = ?",
        (period, reporter_iso2, sitc_code),
    )
    if not rows:
        return 0
    payload = [
        (period, reporter_iso2, partner_iso3, partner_name, sitc_code, float(value))
        for (partner_iso3, partner_name, value) in rows
        if value is not None
    ]
    if not payload:
        return 0
    conn.executemany(
        "INSERT INTO trade_comtrade_dep "
        "(period, reporter_iso2, partner_iso3, partner_name, sitc_code, value_usd) "
        "VALUES (?,?,?,?,?,?)",
        payload,
    )
    return len(payload)


def comtrade_dep_partition_exists(
    conn: sqlite3.Connection,
    period: str,
    reporter_iso2: str,
    sitc_code: str,
) -> bool:
    """Has this (period, reporter, sitc) partition been ingested already?

    Used by the ingestor's --only-stale flag to skip combinations the DB
    already has, so a rate-limited rerun picks up where it left off.
    """
    r = conn.execute(
        "SELECT 1 FROM trade_comtrade_dep "
        "WHERE period = ? AND reporter_iso2 = ? AND sitc_code = ? LIMIT 1",
        (period, reporter_iso2, sitc_code),
    ).fetchone()
    return r is not None


def replace_singstat_trade(df: pd.DataFrame, conn: sqlite3.Connection) -> int:
    """Wipe and replace the trade_singstat table from a long-format dataframe.

    Expected columns: period, frequency, flow, product_code, product_label,
    partner_name, partner_iso2, partner_display, value_sgd_thou.

    Dedupes by primary key (period, frequency, flow, product_code, partner_name)
    via INSERT OR REPLACE — the upstream parsers shouldn't produce duplicates,
    but this is defensive against future sheet-shape changes.
    """
    conn.execute("DELETE FROM trade_singstat")
    if df.empty:
        return 0
    cols = ["period", "frequency", "flow", "product_code", "product_label",
            "partner_name", "partner_iso2", "partner_display", "value_sgd_thou"]
    out = df[cols].copy()
    # Drop rows with bad period or value before insert.
    out = out.dropna(subset=["period", "value_sgd_thou"])
    if out.empty:
        return 0
    rows = out.values.tolist()
    conn.executemany(
        "INSERT OR REPLACE INTO trade_singstat "
        "(period, frequency, flow, product_code, product_label, "
        "partner_name, partner_iso2, partner_display, value_sgd_thou) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        rows,
    )
    return len(rows)
