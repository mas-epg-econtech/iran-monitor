#!/usr/bin/env python3
"""
Export SQLite database and configuration data to JSON files for static HTML dashboard.

Usage:
    python scripts/export_json.py

Exports to docs/data/:
    - time_series.json: All time series data
    - trade.json: All trade data
    - metadata.json: Metadata key-value pairs
    - dependency_nodes.json: Dependency node configuration
    - series_config.json: Series registry configuration
"""

import json
import sqlite3
import sys
import os
from pathlib import Path
from datetime import datetime

# Get project root (parent of scripts directory)
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

# Import configuration modules
from dependency_config import DEPENDENCY_NODES, ROOT_NODES
from series_config import SERIES_REGISTRY


def get_db_path():
    """Get the path to the SQLite database."""
    return PROJECT_ROOT / "data" / "dashboard.db"


def ensure_output_dir():
    """Create output directory if it doesn't exist."""
    output_dir = PROJECT_ROOT / "docs" / "data"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def export_time_series(db_path, output_dir):
    """Export time_series table to nested JSON (grouped by series_id).

    Output shape:
    {
      "<series_id>": {
        "series_name": "...", "source": "...", "unit": "...", "frequency": "...",
        "data": [["YYYY-MM-DD", value], ...]
      }
    }
    This is ~3-4x smaller than a flat list and much faster to index in the browser.
    """
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute(
            "SELECT date, value, series_id, series_name, source, unit, frequency "
            "FROM time_series ORDER BY series_id, date"
        )
        rows = cursor.fetchall()

        series: dict = {}
        total_pts = 0
        for row in rows:
            sid = row["series_id"]
            if sid not in series:
                series[sid] = {
                    "series_name": row["series_name"],
                    "source": row["source"],
                    "unit": row["unit"],
                    "frequency": row["frequency"],
                    "data": [],
                }
            val = round(row["value"], 2) if row["value"] is not None else None
            series[sid]["data"].append([row["date"], val])
            total_pts += 1

        output_file = output_dir / "time_series.json"
        with open(output_file, "w") as f:
            json.dump(series, f, separators=(",", ":"))

        conn.close()
        return total_pts, output_file.stat().st_size

    except Exception as e:
        print(f"Error exporting time_series: {e}")
        return 0, 0


def export_trade(db_path, output_dir):
    """Export trade table to JSON."""
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM trade")
        rows = cursor.fetchall()

        data = []
        for row in rows:
            row_dict = dict(row)
            # Round TradeValue to 0 decimal places
            if "TradeValue in 1000 USD" in row_dict and row_dict["TradeValue in 1000 USD"] is not None:
                row_dict["TradeValue in 1000 USD"] = round(row_dict["TradeValue in 1000 USD"])
            data.append(row_dict)

        output_file = output_dir / "trade.json"
        with open(output_file, "w") as f:
            json.dump(data, f, separators=(",", ":"))

        conn.close()
        return len(data), output_file.stat().st_size

    except Exception as e:
        print(f"Error exporting trade: {e}")
        return 0, 0


def export_metadata(db_path, output_dir):
    """Export metadata table to JSON."""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT key, value FROM metadata")
        rows = cursor.fetchall()

        data = {key: value for key, value in rows}

        output_file = output_dir / "metadata.json"
        with open(output_file, "w") as f:
            json.dump(data, f, indent=2)

        conn.close()
        return len(data), output_file.stat().st_size

    except Exception as e:
        print(f"Error exporting metadata: {e}")
        return 0, 0


def export_dependency_nodes(output_dir):
    """Export dependency nodes and root nodes from config."""
    try:
        data = {
            "DEPENDENCY_NODES": DEPENDENCY_NODES,
            "ROOT_NODES": ROOT_NODES,
        }

        output_file = output_dir / "dependency_nodes.json"
        with open(output_file, "w") as f:
            json.dump(data, f, indent=2)

        return len(DEPENDENCY_NODES) + len(ROOT_NODES), output_file.stat().st_size

    except Exception as e:
        print(f"Error exporting dependency_nodes: {e}")
        return 0, 0


def export_series_config(output_dir):
    """Export series registry from config."""
    try:
        output_file = output_dir / "series_config.json"
        with open(output_file, "w") as f:
            json.dump(SERIES_REGISTRY, f, indent=2)

        return len(SERIES_REGISTRY), output_file.stat().st_size

    except Exception as e:
        print(f"Error exporting series_config: {e}")
        return 0, 0


def main():
    """Main export function."""
    db_path = get_db_path()

    # Check if database exists
    if not db_path.exists():
        print(f"Error: Database not found at {db_path}")
        sys.exit(1)

    print(f"Exporting data from {db_path}")
    print()

    # Ensure output directory exists
    output_dir = ensure_output_dir()
    print(f"Output directory: {output_dir}")
    print()

    # Export all data
    results = {}

    print("Exporting time_series...")
    time_series_count, time_series_size = export_time_series(db_path, output_dir)
    results["time_series.json"] = {"rows": time_series_count, "size_bytes": time_series_size}
    print(f"  ✓ Exported {time_series_count} rows ({time_series_size:,} bytes)")

    print("Exporting trade...")
    trade_count, trade_size = export_trade(db_path, output_dir)
    results["trade.json"] = {"rows": trade_count, "size_bytes": trade_size}
    print(f"  ✓ Exported {trade_count} rows ({trade_size:,} bytes)")

    print("Exporting metadata...")
    metadata_count, metadata_size = export_metadata(db_path, output_dir)
    results["metadata.json"] = {"rows": metadata_count, "size_bytes": metadata_size}
    print(f"  ✓ Exported {metadata_count} key-value pairs ({metadata_size:,} bytes)")

    print("Exporting dependency_nodes...")
    dep_nodes_count, dep_nodes_size = export_dependency_nodes(output_dir)
    results["dependency_nodes.json"] = {"rows": dep_nodes_count, "size_bytes": dep_nodes_size}
    print(f"  ✓ Exported {dep_nodes_count} nodes ({dep_nodes_size:,} bytes)")

    print("Exporting series_config...")
    series_count, series_size = export_series_config(output_dir)
    results["series_config.json"] = {"rows": series_count, "size_bytes": series_size}
    print(f"  ✓ Exported {series_count} series ({series_size:,} bytes)")

    print()
    print("=" * 60)
    print("Export Summary")
    print("=" * 60)
    total_size = sum(r["size_bytes"] for r in results.values())
    total_rows = sum(r["rows"] for r in results.values())

    for filename, info in results.items():
        print(f"{filename:30s} {info['rows']:>8,} rows {info['size_bytes']:>12,} bytes")

    print("-" * 60)
    print(f"{'TOTAL':30s} {total_rows:>8,} rows {total_size:>12,} bytes")
    print("=" * 60)
    print()
    print(f"Export completed at {datetime.now().isoformat()}")


if __name__ == "__main__":
    main()
