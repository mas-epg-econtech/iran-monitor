"""
Financial markets fetchers — yfinance + ADB AsianBondsOnline + Investing.com.

Writes directly to `iran_monitor.db`'s time_series table (no separate
asean_markets.db). Replaces the older `scripts/markets/ingest_tier1.py`
and `scripts/markets/ingest_tier2.py`, which wrote to a sibling DB.

Three fetcher functions, each callable from update_data.py:

  fetch_yfinance_financial_markets(conn, replace_series) -> int
    - 7 FX vs USD (IDR, MYR, PHP, THB, VND, JPY, CNY)
    - 1 bond yield (US 10Y)
    - 3 commodities (Brent ICE, COMEX Gold, COMEX Copper)
    Backfills ~365 days per call; uses replace_series.

  fetch_adb_bond_yields(conn) -> int
    - 5 ASEAN+VN 10Y sovereign yields (ID, MY, PH, TH, VN)
    Single value per call (today). Upserts; preserves prior history.

  fetch_investing_commodities(conn) -> int
    - 7 commodities (Nickel LME, CPO MYR, Rubber TSR20, JKM LNG, Coal
      Newcastle, Aluminum LME, SHFE Nickel)
    Single value per call. Upserts.

Run-time dependencies:
  - yfinance (for the yfinance block)
  - beautifulsoup4 (for the ADB scrape)
  - PROXY_URL env var optional (only used by investing.com — yfinance and
    ADB go direct).
"""
from __future__ import annotations

import os
import re
import sqlite3
import time
from datetime import datetime, timedelta
from urllib.error import URLError, HTTPError
from urllib.request import urlopen, Request, build_opener, ProxyHandler, HTTPSHandler

import pandas as pd


# ════════════════════════════════════════════════════════════════════════
# yfinance — FX, US 10Y, COMEX commodities
# ════════════════════════════════════════════════════════════════════════
YFINANCE_TICKERS = {
    # series_id : (yfinance_ticker, series_name, unit, category)
    "IDR":    ("IDR=X", "Indonesian Rupiah",                 "per USD",   "fx"),
    "MYR":    ("MYR=X", "Malaysian Ringgit",                 "per USD",   "fx"),
    "PHP":    ("PHP=X", "Philippine Peso",                   "per USD",   "fx"),
    "THB":    ("THB=X", "Thai Baht",                         "per USD",   "fx"),
    "VND":    ("VND=X", "Vietnamese Dong",                   "per USD",   "fx"),
    "JPY":    ("JPY=X", "Japanese Yen",                      "per USD",   "fx"),
    "CNY":    ("CNY=X", "Chinese Yuan",                      "per USD",   "fx"),
    "US_10Y": ("^TNX",  "US 10Y Treasury Yield",             "% pa",      "bond"),
    "BRENT":  ("BZ=F",  "Brent Crude Oil (ICE Futures)",     "USD/bbl",   "commodity"),
    "GOLD":   ("GC=F",  "Gold Futures (COMEX)",              "USD/oz",    "commodity"),
    "COPPER": ("HG=F",  "Copper Futures (COMEX)",            "USD/lb",    "commodity"),
    # ALI=F = LME Aluminum 3-month future on yfinance. Gives ~365 days
    # of daily history (vs investing.com's day-by-day accumulation).
    "ALUMINUM": ("ALI=F", "Aluminum (LME 3M)",                "USD/tonne", "commodity"),
    # JKM=F = ICE JKM LNG futures. ~12 years of daily history. Replaces
    # the day-by-day investing.com scrape.
    "JKM_LNG":  ("JKM=F", "JKM LNG Futures (ICE)",            "USD/MMBtu", "commodity"),
}

YFINANCE_BACKFILL_DAYS = 365   # daily history per refresh


def fetch_yfinance_financial_markets(conn, replace_series) -> int:
    """Pull ~365 days of daily history per ticker from yfinance and
    replace_series-write to time_series. Returns total rows written."""
    try:
        import yfinance as yf
    except ImportError:
        print("    SKIP   yfinance not installed (pip install yfinance)")
        return 0

    total = 0
    start = (datetime.now() - timedelta(days=YFINANCE_BACKFILL_DAYS)).strftime("%Y-%m-%d")
    for sid, (ticker, name, unit, _category) in YFINANCE_TICKERS.items():
        try:
            t = yf.Ticker(ticker)
            hist = t.history(start=start)
            if hist.empty:
                print(f"    SKIP   {sid:8s} no data from yfinance:{ticker}")
                continue
            df = pd.DataFrame({
                "date":        hist.index.strftime("%Y-%m-%d"),
                "value":       hist["Close"].astype(float).values,
                "series_id":   sid,
                "series_name": name,
                "source":      f"yfinance:{ticker.lower().replace('=', '').replace('^', '')}",
                "unit":        unit,
                "frequency":   "Daily",
            })
            n = replace_series(sid, df, conn)
            total += n
            print(f"    OK     {sid:8s} {name:36s} {n} pts")
        except Exception as e:
            print(f"    ERROR  {sid:8s} {ticker}: {e}")
    return total


# ════════════════════════════════════════════════════════════════════════
# ADB AsianBondsOnline — scrape "10 Year" yield off each country page
# ════════════════════════════════════════════════════════════════════════
ADB_BONDS: dict = {
    # ADB AsianBondsOnline scrapes — DISABLED 2026-04-30. Migrated to
    # CEIC-sourced daily series (deeper history, same daily cadence).
    # See series_config.py entries for ID/MY/PH/TH/VN_10Y. Kept the
    # config dict in case we want to re-enable as a backup source.
    #
    # "ID_10Y": ("indonesia",   "Indonesia 10Y Govt Bond Yield"),
    # "MY_10Y": ("malaysia",    "Malaysia 10Y Govt Bond Yield"),
    # "PH_10Y": ("philippines", "Philippines 10Y Govt Bond Yield"),
    # "TH_10Y": ("thailand",    "Thailand 10Y Govt Bond Yield"),
    # "VN_10Y": ("vietnam",     "Vietnam 10Y Govt Bond Yield"),
}
ADB_BASE_URL = "https://asianbondsonline.adb.org"

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
              "image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "identity",
    "Cache-Control": "no-cache",
    "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"macOS"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Upgrade-Insecure-Requests": "1",
}

REQUEST_DELAY_SEC = 3.0


def _scrape_adb_yield(slug: str) -> float | None:
    """Pull the '10 Year' yield off https://asianbondsonline.adb.org/<slug>/.
    Returns float or None on failure."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        print("    SKIP   beautifulsoup4 not installed (pip install beautifulsoup4)")
        return None
    url = f"{ADB_BASE_URL}/{slug}/"
    req = Request(url, headers=BROWSER_HEADERS)
    try:
        resp = urlopen(req, timeout=15)
        html = resp.read().decode("utf-8")
    except (URLError, HTTPError) as e:
        print(f"    ERROR  ADB {slug}: {e}")
        return None
    soup = BeautifulSoup(html, "html.parser")
    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cells = row.find_all(["td", "th"])
            if len(cells) >= 2 and cells[0].get_text(strip=True) == "10 Year":
                m = re.match(r"([\d.]+)", cells[1].get_text(strip=True))
                if m:
                    return float(m.group(1))
    print(f"    WARN   ADB {slug}: no '10 Year' row found")
    return None


def fetch_adb_bond_yields(conn) -> int:
    """Scrape today's 10Y yield for each ADB country and upsert into
    time_series. Preserves prior history (single-row-per-day source)."""
    today = datetime.now().strftime("%Y-%m-%d")
    written = 0
    for sid, (slug, name) in ADB_BONDS.items():
        v = _scrape_adb_yield(slug)
        if v is None:
            continue
        conn.execute(
            "INSERT INTO time_series "
            "(date, value, series_id, series_name, source, unit, frequency) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(date, series_id) DO UPDATE SET "
            "value=excluded.value, source=excluded.source",
            (today, v, sid, name, "adb:asianbondsonline", "% pa", "Daily"),
        )
        written += 1
        print(f"    OK     {sid:8s} {name:36s} {v:.3f} % ({today})")
        time.sleep(REQUEST_DELAY_SEC)
    conn.commit()
    return written


# ════════════════════════════════════════════════════════════════════════
# Investing.com — scrape latest commodity prices via residential proxy
# ════════════════════════════════════════════════════════════════════════
INVESTING_COMMODITIES = {
    # series_id : (url, series_name, unit)
    # NICKEL — DISABLED 2026-04-30. Migrated to CEIC LME closing-price series
    # (source_key 486346707) for daily history backfill. See series_config.py.
    # "NICKEL":     ("https://www.investing.com/commodities/nickel",
    #                "Nickel Futures (LME)",                  "USD/tonne"),
    "CPO":          ("https://www.investing.com/commodities/palm-oil",
                     "Crude Palm Oil (Bursa Malaysia FCPO)",  "MYR/tonne"),
    # RUBBER_TSR20 — DISABLED 2026-04-30. Migrated to CEIC source 37594201
    # (Rubber Authority of Thailand, STR 20 Bangkok 2nd-month FOB, THB/kg).
    # Note: unit changed from USc/kg to THB/kg — same benchmark, native
    # currency. Update the commodity card description if mixing with
    # historical USc data.
    # "RUBBER_TSR20": ("https://www.investing.com/commodities/rubber-tsr20-futures",
    #                  "Rubber TSR20 Futures (SGX)",            "USc/kg"),
    # JKM_LNG — DISABLED 2026-04-30. Migrated to yfinance JKM=F for daily
    # history backfill (~12 years vs. investing.com's day-by-day).
    # "JKM_LNG":   ("https://www.investing.com/commodities/lng-japan-korea-marker-platts-futures",
    #               "JKM LNG Futures (Platts)",              "USD/MMBtu"),
    "COAL_NEWC":    ("https://www.investing.com/commodities/newcastle-coal-futures",
                     "Thermal Coal (Newcastle FOB)",          "USD/tonne"),
    # ALUMINUM moved to yfinance (ALI=F) for daily history backfill —
    # see YFINANCE_TICKERS above. Kept here as a comment for reference.
    # SHFE_NICKEL omitted — no working investing.com URL slug found
    # (`shanghai-shfe-nickel-futures`, `shanghai-nickel-futures`, etc.
    # all return HTTP 404). LME Nickel covers the global nickel story
    # for the Iran/Hormuz narrative; SHFE-local pricing isn't critical.
    # If we want it back, candidates to test: `nickel-1`,
    # `shanghai-futures-exchange-nickel`. Or scrape via TradingEconomics.
}

# Default: no proxy. Set PROXY_URL=http://localhost:8080 (or other) when
# running on a server whose IP is blocked by Investing.com / Cloudflare.
PROXY_URL = os.environ.get("PROXY_URL", "").strip()


def _open_via_proxy(req: Request, timeout: int = 20):
    if PROXY_URL:
        opener = build_opener(
            ProxyHandler({"http": PROXY_URL, "https": PROXY_URL}),
            HTTPSHandler(),
        )
        return opener.open(req, timeout=timeout)
    return urlopen(req, timeout=timeout)


def _scrape_investing_price(url: str) -> float | None:
    """Pull "last" price off an investing.com commodity page. Routes through
    PROXY_URL if set. Returns float or None on failure / Cloudflare block."""
    req = Request(url, headers=BROWSER_HEADERS)
    try:
        resp = _open_via_proxy(req, timeout=20)
        html = resp.read().decode("utf-8", errors="replace")
    except (URLError, HTTPError) as e:
        print(f"    ERROR  investing.com {url.rsplit('/', 1)[-1]}: {e}")
        return None
    if len(html) < 5000 or "just a moment" in html.lower():
        print(f"    WARN   investing.com {url.rsplit('/', 1)[-1]}: "
              f"Cloudflare challenge ({len(html)} bytes)")
        return None
    last = re.search(r'"last"\s*:\s*([\d.]+)', html)
    if last:
        return float(last.group(1))
    # Fallback patterns for different page layouts
    for pat in (
        r'"price"\s*:\s*"?([\d,.]+)"?',
        r'"currentPrice"\s*:\s*"?([\d,.]+)"?',
        r'data-test="instrument-price-last"[^>]*>([\d,.]+)',
    ):
        m = re.search(pat, html)
        if m:
            return float(m.group(1).replace(",", ""))
    return None


def fetch_investing_commodities(conn) -> int:
    """Scrape today's price for each investing.com commodity. Upserts."""
    today = datetime.now().strftime("%Y-%m-%d")
    written = 0
    for sid, (url, name, unit) in INVESTING_COMMODITIES.items():
        v = _scrape_investing_price(url)
        if v is None:
            continue
        # Map series_id → source key (matches the existing convention in the DB)
        source_key = "investing.com:" + sid.lower().replace("_", "-")
        conn.execute(
            "INSERT INTO time_series "
            "(date, value, series_id, series_name, source, unit, frequency) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(date, series_id) DO UPDATE SET "
            "value=excluded.value, source=excluded.source",
            (today, v, sid, name, source_key, unit, "Daily"),
        )
        written += 1
        print(f"    OK     {sid:14s} {name:42s} {v:>10,.2f} {unit} ({today})")
        time.sleep(REQUEST_DELAY_SEC)
    conn.commit()
    return written
