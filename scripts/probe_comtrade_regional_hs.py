#!/usr/bin/env python3
"""
UN Comtrade discovery probe — does HS-Annual mode have BETTER 2025 coverage
than SITC-Annual mode (which only had 3-of-10 reporters with 2025 data as
of the previous probe, see REGIONAL_TRADE_NOTES.md §4)?

Same 10 regional reporters, same 3 years (2023/24/25), same 2 partners
(World, Singapore). Only the classification + endpoint changes:
  - Endpoint: /data/v1/get/C/A/HS  (was /data/v1/get/C/A/S4)
  - Probe code: HS chapter '28' (Inorganic chemicals)
                 (was SITC '5' chapter total)

Why HS 28 specifically: it's the most universally reported chemical
chapter (all 10 reporters trade inorganic chemicals; almost no zero-sum
issues). Single-chapter probe is sufficient — we just need to know if
the reporter has ANY 2025 annual filing in HS mode. If yes, the full
ingest will work for all chemical/fuel HS chapters too.

Quota: 10 reporters × 2 partners × 3 years = 60 calls.

Run:
  python3.11 scripts/probe_comtrade_regional_hs.py

Compare the resulting hit/miss matrix to the SITC probe's matrix
(documented in REGIONAL_TRADE_NOTES.md §4).
"""
from __future__ import annotations

import os
import sys
import time
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


REGIONAL_REPORTERS = {
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

SINGAPORE_PARTNER_CODE = "702"
WORLD_PARTNER_CODE     = "0"

# HS chapter 28 = Inorganic chemicals — single broad chapter.
PROBE_HS_CODE = "28"

# Comtrade HS-Annual endpoint. Same shape as the S4 endpoint, just /HS.
COMTRADE_URL = "https://comtradeapi.un.org/data/v1/get/C/A/HS"

HISTORICAL_PROBES = [
    ("2025", "2025"),
    ("2024", "2024"),
    ("2023", "2023"),
]


def _get_with_retry(params: dict, headers: dict, max_retries: int = 5):
    import requests
    delay = 2.0
    for attempt in range(max_retries):
        try:
            resp = requests.get(COMTRADE_URL, params=params, headers=headers, timeout=30)
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
            retry_after = resp.headers.get("Retry-After")
            wait = float(retry_after) if retry_after and retry_after.isdigit() else delay
            time.sleep(wait)
            delay *= 2
            continue
        return resp.status_code, None
    return 429, None


def probe_one(reporter_code: str, partner_code: str, period: str, headers: dict) -> dict:
    params = {
        "reporterCode": reporter_code,
        "partnerCode":  partner_code,
        "period":       period,
        "cmdCode":      PROBE_HS_CODE,
        "flowCode":     "M",  # Imports
        "includeDesc":  "true",
    }
    status, payload = _get_with_retry(params, headers)
    if status == 429:
        return {"status": "RATE_LIMITED_AFTER_RETRIES"}
    if status != 200:
        return {"status": f"HTTP {status}"}
    rows = (payload or {}).get("data") or []
    if not rows:
        return {"status": "NO_DATA"}
    # For partnerCode=0 (World), Comtrade returns multiple rows split by
    # partner2Code. The total trade value is the SUM across all rows
    # (see probe_comtrade_world_aggregation.py for the diagnosis).
    if partner_code == WORLD_PARTNER_CODE:
        total = sum(r.get("primaryValue", 0) or 0 for r in rows)
        return {"status": "OK", "n_rows": len(rows), "trade_value": total}
    else:
        # Singapore as partner returns a single row (or a few sub-rows)
        total = sum(r.get("primaryValue", 0) or 0 for r in rows)
        return {"status": "OK", "n_rows": len(rows), "trade_value": total}


def main() -> None:
    api_key = os.environ.get("COMTRADE_API_KEY", "")
    if not api_key:
        sys.exit("COMTRADE_API_KEY not set in .env.")
    headers = {"Ocp-Apim-Subscription-Key": api_key, "Accept": "application/json"}

    print(f"Probing Comtrade HS ANNUAL mode — chapter {PROBE_HS_CODE} "
          f"(Inorganic chemicals), Imports.")
    print(f"  Years: {[p for _, p in HISTORICAL_PROBES]}")
    print(f"  10 reporters × 2 partners × 3 years = 60 calls max, with retry+backoff.\n")

    historical_results: dict[str, dict] = {}
    for iso, (name, code) in REGIONAL_REPORTERS.items():
        per_iso = {}
        for label, period in HISTORICAL_PROBES:
            rw = probe_one(code, WORLD_PARTNER_CODE, period, headers)
            time.sleep(1.5)
            rs = probe_one(code, SINGAPORE_PARTNER_CODE, period, headers)
            time.sleep(1.5)
            per_iso[label] = (rw, rs)
        historical_results[iso] = per_iso
        marks = []
        for label, _ in HISTORICAL_PROBES:
            rw, rs = per_iso[label]
            wok = rw.get("status") == "OK"
            sok = rs.get("status") == "OK"
            if wok and sok:
                marks.append(f"{label}=✓")
            elif rw.get("status") == "RATE_LIMITED_AFTER_RETRIES" or rs.get("status") == "RATE_LIMITED_AFTER_RETRIES":
                marks.append(f"{label}=⏱")
            elif rw.get("status") == "NO_DATA" or rs.get("status") == "NO_DATA":
                marks.append(f"{label}=∅")
            else:
                marks.append(f"{label}=✗")
        print(f"  {iso}  {name:<14s}  {'  '.join(marks)}")

    # ── Summary table — historical SG share over time ────────────────────
    print()
    print("=" * 78)
    print(f"  SG share of HS chapter {PROBE_HS_CODE} (Inorganic chemicals) imports — annual")
    print("=" * 78)
    print(f"  {'ISO':<4s} {'Reporter':<14s} ", end="")
    for label, _ in HISTORICAL_PROBES:
        print(f"{label:>10s}", end="")
    print()
    print(f"  {'-'*4} {'-'*14}{'-'*10*len(HISTORICAL_PROBES)}")
    for iso, (name, _) in REGIONAL_REPORTERS.items():
        per_iso = historical_results.get(iso, {})
        print(f"  {iso:<4s} {name:<14s} ", end="")
        for label, _ in HISTORICAL_PROBES:
            rw, rs = per_iso.get(label, ({}, {}))
            wv = rw.get("trade_value")
            sv = rs.get("trade_value")
            if isinstance(wv, (int, float)) and isinstance(sv, (int, float)) and wv > 0:
                print(f"{(sv/wv*100):>9.2f}%", end="")
            else:
                wstat = rw.get("status", "?")
                sstat = rs.get("status", "?")
                tag = "∅" if "NO_DATA" in (wstat, sstat) else ("⏱" if "RATE" in str(wstat)+str(sstat) else "✗")
                print(f"{tag:>10s}", end="")
        print()

    print()
    print("Legend: ✓ data + share computed | ∅ NO_DATA from Comtrade | ⏱ rate-limited even with retries | ✗ other error")
    print()
    print("Compare against the SITC-Annual probe matrix in REGIONAL_TRADE_NOTES.md §4.")


if __name__ == "__main__":
    main()
