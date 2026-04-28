"""
Download IMF PortWatch Daily Data
=================================
Downloads the latest Daily Ports Data and Daily Chokepoints Data
from IMF PortWatch via the ArcGIS Feature Service REST API.

The data is publicly available at:
  - Ports:       https://portwatch.imf.org/datasets/4a3facf6df3542b09dbe48d5556b45fa/about
  - Chokepoints: https://portwatch.imf.org/datasets/42132aa4e2fc4d41bdaf9a445f688931/about

No API key required — the data is public.

Usage:
  python download_portwatch_data.py              # incremental update (both datasets)
  python download_portwatch_data.py --ports      # incremental update (ports only)
  python download_portwatch_data.py --chokepoints # incremental update (chokepoints only)
  python download_portwatch_data.py --full        # full re-download (both datasets)

Incremental mode (default):
  - Checks the latest date in the existing CSV
  - Downloads only records after that date from the API
  - Appends new records to the existing CSV
  - If no existing CSV, does a full download

Full mode (--full):
  - Downloads the entire dataset and overwrites existing files

Output:
  data/portwatch/Daily_Ports_Data.csv
  data/portwatch/Daily_Chokepoints_Data.csv

Notes:
  - Full ports data is ~5M+ records; expect ~15-30 minutes.
  - Incremental updates typically take 1-5 minutes depending on how many
    days of new data are available.
  - Chokepoints data is small (~75K records full); downloads in <1 minute.
  - The script paginates through the ArcGIS Feature Service API (max 2000
    records per request).
  - Date fields (epoch-ms in the API) are converted to YYYY-MM-DD strings.
"""

import csv
import json
import os
import sys
import time
from datetime import datetime, timedelta
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError
from urllib.parse import quote

# ── Configuration ──────────────────────────────────────────────────────

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # Iran Monitor/ (script is at Iran Monitor/scripts/shipping/)
OUT_DIR = os.path.join(BASE_DIR, "data", "portwatch")
os.makedirs(OUT_DIR, exist_ok=True)

# ArcGIS Feature Service endpoints
PORTS_URL = (
    "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services"
    "/Daily_Ports_Data/FeatureServer/0"
)
CHOKEPOINTS_URL = (
    "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services"
    "/Daily_Chokepoints_Data/FeatureServer/0"
)

# ArcGIS query parameters
PAGE_SIZE = 2000        # max records per request (ArcGIS limit is often 2000)
MAX_RETRIES = 3         # retries per request on failure
RETRY_DELAY = 5         # seconds between retries
REQUEST_DELAY = 0.5     # seconds between paginated requests (rate-limit courtesy)


# ── Helpers ────────────────────────────────────────────────────────────

def fetch_json(url, params=None, retries=MAX_RETRIES):
    """Fetch JSON from a URL with retry logic."""
    if params:
        query = "&".join(f"{k}={v}" for k, v in params.items())
        full_url = f"{url}?{query}"
    else:
        full_url = url

    for attempt in range(retries):
        try:
            req = Request(full_url, headers={"User-Agent": "PortWatch-Downloader/1.0"})
            with urlopen(req, timeout=120) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError) as e:
            if attempt < retries - 1:
                wait = RETRY_DELAY * (attempt + 1)
                print(f"  Retry {attempt + 1}/{retries} after error: {e} (waiting {wait}s)")
                time.sleep(wait)
            else:
                raise


def get_record_count(service_url, where="1=1"):
    """Get the number of records matching a WHERE clause."""
    data = fetch_json(f"{service_url}/query", {
        "where": quote(where),
        "returnCountOnly": "true",
        "f": "json",
    })
    return data.get("count", 0)


def get_fields(service_url):
    """Get field names and types from the feature service metadata."""
    data = fetch_json(service_url, {"f": "json"})
    fields = data.get("fields", [])
    return [(f["name"], f["type"]) for f in fields]


def get_max_date_from_csv(csv_path, date_col="date"):
    """
    Read the existing CSV and return the max date string.
    Handles both 'YYYY/MM/DD' and 'YYYY/MM/DD HH:MM:SS+00' formats.
    Returns a datetime object, or None if file doesn't exist or is empty.
    """
    if not os.path.exists(csv_path):
        return None

    max_date = None
    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            date_str = row.get(date_col, "").strip()
            if not date_str:
                continue
            # Parse date — handle both formats
            try:
                if " " in date_str:
                    # "2026/04/05 00:00:00+00" format
                    dt = datetime.strptime(date_str.split("+")[0].strip(), "%Y/%m/%d %H:%M:%S")
                elif "-" in date_str:
                    # "2026-04-05" format (from API download)
                    dt = datetime.strptime(date_str, "%Y-%m-%d")
                else:
                    # "2026/04/05" format
                    dt = datetime.strptime(date_str, "%Y/%m/%d")

                if max_date is None or dt > max_date:
                    max_date = dt
            except ValueError:
                continue

    return max_date


def date_to_epoch_ms(dt):
    """Convert a datetime to epoch milliseconds (for ArcGIS WHERE clause)."""
    epoch = datetime(1970, 1, 1)
    return int((dt - epoch).total_seconds() * 1000)


def download_feature_service(service_url, out_path, label="data",
                              where="1=1", append=False):
    """
    Download records from an ArcGIS Feature Service layer to CSV.

    Args:
        service_url: ArcGIS Feature Service endpoint
        out_path: Output CSV path
        label: Display label for logging
        where: WHERE clause for filtering records
        append: If True, append to existing file instead of overwriting
    """
    print(f"\n{'='*60}")
    print(f"Downloading {label}")
    if where != "1=1":
        print(f"  Filter: {where}")
    print(f"{'='*60}")

    # 1. Get record count for this query
    total = get_record_count(service_url, where)
    print(f"  Records matching query: {total:,}")

    if total == 0:
        print("  No new records to download.")
        return True  # Not a failure — just nothing new

    # 2. Get field metadata
    fields_meta = get_fields(service_url)
    field_names = [name for name, _ in fields_meta]
    date_fields = {name for name, ftype in fields_meta if ftype == "esriFieldTypeDate"}
    print(f"  Fields: {len(field_names)}")

    # 3. Paginated download
    all_rows = []
    offset = 0
    page = 0
    start_time = time.time()

    while offset < total:
        page += 1
        params = {
            "where": quote(where),
            "outFields": "*",
            "orderByFields": "ObjectId",
            "resultOffset": str(offset),
            "resultRecordCount": str(PAGE_SIZE),
            "f": "json",
        }

        data = fetch_json(f"{service_url}/query", params)
        features = data.get("features", [])

        if not features:
            break

        for feat in features:
            attrs = feat.get("attributes", {})
            # Convert epoch-ms dates to readable strings (YYYY/MM/DD to match existing data)
            for df in date_fields:
                if df in attrs and attrs[df] is not None:
                    try:
                        attrs[df] = datetime.utcfromtimestamp(
                            attrs[df] / 1000
                        ).strftime("%Y/%m/%d")
                    except (ValueError, OSError):
                        pass
            all_rows.append(attrs)

        fetched = len(all_rows)
        elapsed = time.time() - start_time
        rate = fetched / elapsed if elapsed > 0 else 0
        eta = (total - fetched) / rate if rate > 0 else 0
        print(
            f"  Page {page}: {fetched:,}/{total:,} records "
            f"({fetched/total*100:.1f}%) "
            f"[{rate:.0f} rec/s, ETA {eta:.0f}s]"
        )

        offset += len(features)

        # Stop if we've fetched all records or server says no more
        if len(all_rows) >= total:
            break
        if not data.get("exceededTransferLimit", False) and len(features) == 0:
            break

        time.sleep(REQUEST_DELAY)

    elapsed = time.time() - start_time
    print(f"  Downloaded {len(all_rows):,} records in {elapsed:.1f}s")

    if not all_rows:
        print("  WARNING: No records downloaded!")
        return False

    # 4. Determine columns
    data_keys = set(all_rows[0].keys())
    columns = [f for f in field_names if f in data_keys]
    for k in all_rows[0].keys():
        if k not in columns:
            columns.append(k)

    # 5. Write CSV (append or overwrite)
    if append and os.path.exists(out_path):
        # Read existing header to ensure column order matches
        with open(out_path, "r", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            existing_header = next(reader)
        # Use existing column order
        columns = existing_header

        with open(out_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
            writer.writerows(all_rows)
        print(f"  Appended {len(all_rows):,} records to: {out_path}")
    else:
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(all_rows)
        print(f"  Saved to: {out_path}")

    file_size = os.path.getsize(out_path)
    print(f"  File size: {file_size / 1024 / 1024:.1f} MB")

    return True


# ── Validation ─────────────────────────────────────────────────────────

def validate_csv(path, expected_min_rows, label):
    """Basic validation of downloaded CSV."""
    with open(path, "r", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        header = next(reader)
        row_count = sum(1 for _ in reader)

    print(f"\n  Validation ({label}):")
    print(f"    Columns: {len(header)}")
    print(f"    Rows: {row_count:,}")

    if row_count < expected_min_rows:
        print(f"    WARNING: Expected at least {expected_min_rows:,} rows!")
        return False

    header_lower = [h.lower() for h in header]
    if "date" not in header_lower and "year" not in header_lower:
        print("    WARNING: No 'date' or 'year' column found!")
        return False

    print("    OK")
    return True


# ── Incremental Update ────────────────────────────────────────────────

def incremental_update(service_url, csv_path, label, min_rows_full):
    """
    Incrementally update a PortWatch CSV:
      1. Check the latest date in the existing CSV
      2. Query the API for records after that date
      3. Append new records to the CSV

    Falls back to full download if no existing CSV.
    """
    max_date = get_max_date_from_csv(csv_path)

    if max_date is None:
        print(f"\n  No existing data found. Doing full download.")
        ok = download_feature_service(service_url, csv_path, label)
        if ok:
            validate_csv(csv_path, min_rows_full, label)
        return ok

    print(f"\n  Existing data through: {max_date.strftime('%Y-%m-%d')}")

    # Query for records strictly after the max date
    # Use SQL date string format (epoch-ms doesn't work with all ArcGIS services)
    after_date = max_date + timedelta(days=1)
    after_str = after_date.strftime('%Y-%m-%d')
    where = f"date >= '{after_str}'"

    print(f"  Querying for records from {after_str} onwards...")

    # Get count first
    new_count = get_record_count(service_url, where)
    print(f"  New records available: {new_count:,}")

    if new_count == 0:
        print("  Data is already up to date.")
        return True

    # Download and append
    ok = download_feature_service(
        service_url, csv_path, f"{label} (incremental)",
        where=where, append=True
    )

    if ok:
        # Verify final state
        new_max = get_max_date_from_csv(csv_path)
        if new_max:
            print(f"  Data now through: {new_max.strftime('%Y-%m-%d')}")

    return ok


# ── Main ───────────────────────────────────────────────────────────────

def main():
    args = sys.argv[1:]
    do_ports = "--ports" in args or (not any(a in args for a in ["--ports", "--chokepoints"]))
    do_chokepoints = "--chokepoints" in args or (not any(a in args for a in ["--ports", "--chokepoints"]))
    full_mode = "--full" in args

    print(f"IMF PortWatch Data Downloader")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Mode: {'full' if full_mode else 'incremental'}")
    print(f"Output directory: {OUT_DIR}")

    success = True

    if do_chokepoints:
        cp_path = os.path.join(OUT_DIR, "Daily_Chokepoints_Data.csv")
        if full_mode:
            ok = download_feature_service(CHOKEPOINTS_URL, cp_path, "Daily Chokepoints Data")
            if ok:
                validate_csv(cp_path, 1_000, "Chokepoints")
        else:
            ok = incremental_update(CHOKEPOINTS_URL, cp_path, "Daily Chokepoints Data", 1_000)
        success = success and ok

    if do_ports:
        ports_path = os.path.join(OUT_DIR, "Daily_Ports_Data.csv")
        if full_mode:
            ok = download_feature_service(PORTS_URL, ports_path, "Daily Ports Data")
            if ok:
                validate_csv(ports_path, 1_000_000, "Ports")
        else:
            ok = incremental_update(PORTS_URL, ports_path, "Daily Ports Data", 1_000_000)
        success = success and ok

    print(f"\n{'='*60}")
    if success:
        print("All downloads completed successfully.")
    else:
        print("Some downloads failed. Check output above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
