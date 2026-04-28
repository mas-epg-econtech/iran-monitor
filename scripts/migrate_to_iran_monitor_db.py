"""
One-shot migration: consolidate dashboard.db (energy/SG indicators) +
asean_markets.db (regional FX/bonds/commodities) into a single
iran_monitor.db with a unified schema.

Schema decisions:
  - Keep the existing time_series shape (date, value, series_id, series_name,
    source, unit, frequency) and add a `category` column for ASEAN-style
    categorization. Energy data gets category=NULL for now (will populate later
    via page_layouts.py).
  - Add separate metadata tables from the ASEAN side: indicators (per-series
    metadata), data_sources (rich attribution), ingestion_log (run history).
  - Carry over the trade table from dashboard.db unchanged (Comtrade SG petroleum).
  - Carry over the metadata table from dashboard.db unchanged (LLM narrative + freshness).

Run from the Iran Monitor root:
  python3 scripts/migrate_to_iran_monitor_db.py
"""
from __future__ import annotations

import shutil
import sqlite3
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

SRC_ENERGY = DATA / "dashboard.db"           # 87 series, 61k rows of time_series + 16k rows of trade + metadata
SRC_MARKETS = DATA / "asean_markets.db"      # 17 indicators, 619 rows of daily_data + indicators + data_sources + ingestion_log
DST_FINAL = DATA / "iran_monitor.db"

# In Cowork, the user's mounted folders are bindfs/FUSE which SQLite can't write
# to reliably (fsync / atomic-rename semantics differ). We build the DB on a real
# local filesystem first, then copy the finished file across.
DST_SCRATCH = Path(tempfile.gettempdir()) / "iran_monitor_build.db"


SCHEMA_SQL = """
-- Time series observations (unified energy + macro + ASEAN markets).
-- Energy/SG data has category=NULL until page_layouts assignment.
-- ASEAN data has category in {fx, bond, commodity}.
CREATE TABLE IF NOT EXISTS time_series (
    date         TEXT NOT NULL,
    value        REAL,
    series_id    TEXT NOT NULL,
    series_name  TEXT,
    source       TEXT,
    unit         TEXT,
    frequency    TEXT,
    category     TEXT,
    PRIMARY KEY (date, series_id)
);
CREATE INDEX IF NOT EXISTS idx_ts_series ON time_series(series_id);
CREATE INDEX IF NOT EXISTS idx_ts_source ON time_series(source);
CREATE INDEX IF NOT EXISTS idx_ts_category ON time_series(category);

-- Per-series metadata (richer than what's denormalized in time_series).
CREATE TABLE IF NOT EXISTS indicators (
    series_id    TEXT PRIMARY KEY,
    series_name  TEXT NOT NULL,
    category     TEXT,
    source       TEXT,
    unit         TEXT,
    frequency    TEXT,
    description  TEXT,
    tier         INTEGER DEFAULT 1
);

-- Data source attribution (carried over from asean_markets.db).
CREATE TABLE IF NOT EXISTS data_sources (
    source_key      TEXT PRIMARY KEY,
    provider        TEXT NOT NULL,
    provider_url    TEXT,
    dataset         TEXT,
    ticker_or_id    TEXT,
    data_url        TEXT,
    frequency       TEXT,
    lag             TEXT,
    license_info    TEXT,
    notes           TEXT
);

-- Ingestion run log.
CREATE TABLE IF NOT EXISTS ingestion_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_at      TEXT NOT NULL,
    source      TEXT NOT NULL,
    status      TEXT NOT NULL,
    records     INTEGER DEFAULT 0,
    message     TEXT
);

-- Singapore Comtrade petroleum (HS 2709) trade by partner — from dashboard.db.
CREATE TABLE IF NOT EXISTS trade (
    period             TEXT,
    year               TEXT,
    month              TEXT,
    nomenclature       TEXT,
    reporter_iso3      TEXT,
    product_code       TEXT,
    reporter_name      TEXT,
    partner_name       TEXT,
    partner_iso3       TEXT,
    trade_flow_name    TEXT,
    trade_flow_code    TEXT,
    trade_value        TEXT
);

-- Free-form key/value metadata (LLM narrative, last-updated timestamps, etc.).
CREATE TABLE IF NOT EXISTS metadata (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


def migrate() -> None:
    if not SRC_ENERGY.exists():
        raise FileNotFoundError(f"Missing source DB: {SRC_ENERGY}")
    if not SRC_MARKETS.exists():
        raise FileNotFoundError(f"Missing source DB: {SRC_MARKETS}")

    # Clean any prior scratch build
    if DST_SCRATCH.exists():
        DST_SCRATCH.unlink()
    journal = DST_SCRATCH.with_suffix(DST_SCRATCH.suffix + "-journal")
    if journal.exists():
        journal.unlink()

    print(f"Building DB at scratch path: {DST_SCRATCH}")
    dst = sqlite3.connect(DST_SCRATCH)
    dst.executescript(SCHEMA_SQL)
    dst.commit()

    # ── 1. Copy time_series from dashboard.db (energy + SG) ──────────────────
    # Source has ~8K duplicate (date, series_id) rows from repeated scrapes.
    # The new schema enforces PK uniqueness; INSERT OR REPLACE keeps the last
    # row encountered per (date, series_id), dedup'ing the source.
    print(f"\n[1/6] Migrating time_series from {SRC_ENERGY.name}")
    src = sqlite3.connect(SRC_ENERGY)
    rows = list(src.execute(
        "SELECT date, value, series_id, series_name, source, unit, frequency FROM time_series"
    ))
    dst.executemany(
        "INSERT OR REPLACE INTO time_series (date, value, series_id, series_name, source, unit, frequency, category) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, NULL)",
        rows,
    )
    dst.commit()
    inserted = dst.execute("SELECT COUNT(*) FROM time_series").fetchone()[0]
    print(f"      Read {len(rows):,} source rows, inserted {inserted:,} unique (deduped {len(rows) - inserted:,})")

    # ── 2. Copy trade and metadata from dashboard.db ─────────────────────────
    print(f"\n[2/6] Migrating trade table from {SRC_ENERGY.name}")
    trade_rows = list(src.execute("SELECT * FROM trade"))
    cols = [c[1] for c in src.execute("PRAGMA table_info(trade)")]
    placeholders = ",".join("?" * len(cols))
    dst.executemany(
        f"INSERT INTO trade ({','.join(cols)}) VALUES ({placeholders})",
        trade_rows,
    )
    dst.commit()
    print(f"      Inserted {len(trade_rows):,} trade rows ({cols})")

    print(f"\n[3/6] Migrating metadata from {SRC_ENERGY.name}")
    meta_rows = list(src.execute("SELECT key, value FROM metadata"))
    dst.executemany("INSERT INTO metadata (key, value) VALUES (?, ?)", meta_rows)
    dst.commit()
    print(f"      Inserted {len(meta_rows)} metadata rows")
    src.close()

    # ── 3. Copy ASEAN markets daily_data → time_series ───────────────────────
    print(f"\n[4/6] Migrating daily_data from {SRC_MARKETS.name} -> time_series")
    src = sqlite3.connect(SRC_MARKETS)
    src.row_factory = sqlite3.Row

    # daily_data schema: date, category, indicator, value, unit, source, ingested_at
    # We need series_name from indicators table to populate time_series.series_name.
    # Build a series_id -> series_name lookup from the indicators table.
    indicator_label = {}
    indicator_freq = {}
    for r in src.execute("SELECT indicator, label, source, tier FROM indicators"):
        indicator_label[r[0]] = r[1]

    # Insert into unified time_series. Frequency: daily for everything in ASEAN markets
    # (that's the current state — Tier 1 daily APIs and Tier 2 daily scrapers).
    asean_rows = []
    for r in src.execute(
        "SELECT date, value, indicator, category, source, unit FROM daily_data"
    ):
        date, value, indicator, category, source, unit = r
        series_name = indicator_label.get(indicator, indicator)
        asean_rows.append((date, value, indicator, series_name, source, unit, "Daily", category))

    dst.executemany(
        "INSERT OR REPLACE INTO time_series (date, value, series_id, series_name, source, unit, frequency, category) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        asean_rows,
    )
    dst.commit()
    asean_inserted = dst.execute(
        "SELECT COUNT(*) FROM time_series WHERE category IN ('fx', 'bond', 'commodity')"
    ).fetchone()[0]
    print(f"      Read {len(asean_rows):,} ASEAN rows, inserted {asean_inserted:,} unique")

    # ── 4. Copy ASEAN indicators table → indicators ───────────────────────────
    print(f"\n[5/6] Migrating indicators metadata from {SRC_MARKETS.name}")
    ind_rows = list(src.execute(
        "SELECT indicator, label, category, source, unit, tier FROM indicators"
    ))
    # Map (indicator, label, category, source, unit, tier) → indicators(series_id, series_name, category, source, unit, tier)
    # Frequency for all ASEAN indicators is daily.
    for r in ind_rows:
        dst.execute(
            "INSERT INTO indicators (series_id, series_name, category, source, unit, frequency, tier) "
            "VALUES (?, ?, ?, ?, ?, 'Daily', ?)",
            r,
        )
    dst.commit()
    print(f"      Inserted {len(ind_rows)} indicator metadata rows")

    # ── 5. Copy data_sources and ingestion_log ───────────────────────────────
    print(f"\n[6/6] Migrating data_sources + ingestion_log from {SRC_MARKETS.name}")
    ds_rows = list(src.execute("SELECT * FROM data_sources"))
    if ds_rows:
        ds_cols = [c[1] for c in src.execute("PRAGMA table_info(data_sources)")]
        placeholders = ",".join("?" * len(ds_cols))
        dst.executemany(
            f"INSERT INTO data_sources ({','.join(ds_cols)}) VALUES ({placeholders})",
            ds_rows,
        )
    print(f"      Inserted {len(ds_rows)} data_sources rows")

    log_rows = list(src.execute("SELECT * FROM ingestion_log"))
    if log_rows:
        log_cols = [c[1] for c in src.execute("PRAGMA table_info(ingestion_log)")]
        placeholders = ",".join("?" * len(log_cols))
        dst.executemany(
            f"INSERT INTO ingestion_log ({','.join(log_cols)}) VALUES ({placeholders})",
            log_rows,
        )
    dst.commit()
    print(f"      Inserted {len(log_rows)} ingestion_log rows")
    src.close()

    # ── Verify ───────────────────────────────────────────────────────────────
    print("\n=== Verification ===")
    for tbl in ["time_series", "trade", "metadata", "indicators", "data_sources", "ingestion_log"]:
        n = dst.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
        print(f"  {tbl}: {n:,} rows")

    print("\n=== time_series breakdown by category ===")
    for cat, n_series, n_rows in dst.execute("""
        SELECT COALESCE(category, '(NULL)'), COUNT(DISTINCT series_id), COUNT(*)
        FROM time_series GROUP BY category ORDER BY COUNT(*) DESC
    """):
        print(f"  {cat:<15} {n_series:>4} series, {n_rows:>7,} rows")

    print("\n=== time_series breakdown by source ===")
    for src_key, n_series, n_rows in dst.execute("""
        SELECT source, COUNT(DISTINCT series_id), COUNT(*)
        FROM time_series GROUP BY source ORDER BY COUNT(*) DESC
    """):
        print(f"  {src_key:<28} {n_series:>4} series, {n_rows:>7,} rows")

    dst.close()

    # Copy the finished DB from scratch to the user's mounted data folder.
    # `shutil.copy` writes byte-by-byte without SQLite-specific syscalls, so it
    # works on the FUSE-backed Cowork mount even though direct SQLite writes don't.
    print(f"\nCopying {DST_SCRATCH} -> {DST_FINAL}")
    shutil.copy(DST_SCRATCH, DST_FINAL)
    DST_SCRATCH.unlink()

    # Size comparison
    e_size = SRC_ENERGY.stat().st_size
    m_size = SRC_MARKETS.stat().st_size
    d_size = DST_FINAL.stat().st_size
    print(f"\nSize: {SRC_ENERGY.name} {e_size/1024/1024:.1f}MB + {SRC_MARKETS.name} {m_size/1024:.0f}KB -> {DST_FINAL.name} {d_size/1024/1024:.1f}MB")
    print(f"\nMigration complete: {DST_FINAL}")


if __name__ == "__main__":
    migrate()
