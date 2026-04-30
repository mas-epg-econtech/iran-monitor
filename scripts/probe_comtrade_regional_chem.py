#!/usr/bin/env python3
"""
UN Comtrade discovery probe — verify monthly chemical-imports data is
available for the 10 regional countries, with both Singapore and World as
partners. Probes in SITC Rev 4 mode (not HS) so the codes match the
SingStat sheet on the SG-side ingestion.

Why SITC: the dashboard's SG-side data (SG_Annual/Monthly_Imports tabs)
uses SITC codes. To compute a clean dependence ratio per regional country,
both numerator (chemical imports from SG) and denominator (chemical imports
from World) need to use the same classification — SITC throughout.

What it does:
  For each of the 10 regional reporters (CN/IN/ID/JP/MY/PH/KR/TW/TH/VN):
    1. Fetch ONE recent month of SITC chapter 5 (Chemicals total) imports
       from World.
    2. Fetch the same with partner=Singapore filter.
    3. Report:
        - Whether data exists at all
        - The latest period available (lag from 'today')
        - Row counts (validates partner=World ≠ partner=Singapore)
        - Trade value sample (sanity check)

  This is a minimal-quota probe — 2 calls × 10 reporters = 20 calls total
  out of the typical free-tier daily limit.

  SITC Rev 4 chapters worth knowing for chemicals:
    SITC 5:   Chemicals (total)               ← probed here
    SITC 51:  Organic chemicals               — would EXCLUDE
    SITC 52:  Inorganic chemicals
    SITC 53:  Dyeing, tanning, colouring
    SITC 54:  Pharmaceutical products         — would EXCLUDE
    SITC 55:  Essential oils, perfumes, cleaning preparations
    SITC 56:  Fertilizers
    SITC 57:  Plastics in primary forms
    SITC 58:  Plastics in non-primary forms
    SITC 59:  Misc chemical materials

  "SITC 5 less 51 less 54" = SITC 5 minus SITC 51 minus SITC 54. We can
  compute it by fetching all three and subtracting (or fetching SITC 52,
  53, 55, 56, 57, 58, 59 individually and summing). The probe just verifies
  that SITC 5 (the total) is fetchable; the deeper sub-codes will be too.

Run from Iran Monitor root with .env present:
  python3.11 scripts/probe_comtrade_regional_chem.py
"""
from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timezone
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


# Comtrade reporter codes for our 10 regional countries.
# Source: https://comtradeapi.un.org/files/v1/app/reference/Reporters.json
REGIONAL_REPORTERS = {
    "CN": ("China",       "156"),
    "IN": ("India",       "699"),
    "ID": ("Indonesia",   "360"),
    "JP": ("Japan",       "392"),
    "MY": ("Malaysia",    "458"),
    "PH": ("Philippines", "608"),
    "KR": ("South Korea", "410"),
    "TW": ("Taiwan",      "490"),  # Comtrade reports Taiwan under "Other Asia, nes"
    "TH": ("Thailand",    "764"),
    "VN": ("Vietnam",     "704"),
}

SINGAPORE_PARTNER_CODE = "702"
WORLD_PARTNER_CODE     = "0"     # Comtrade aggregate "World"

# SITC Rev 4 chapter 5 = Chemicals (total). Annual mode is much more
# reliably populated than monthly across all reporters, which matches our
# actual need: 3 stable data points per country (2023/24/25) showing the
# dependence-on-SG trend, not a noisy monthly time series.
PROBE_SITC_CODE = "5"

# Comtrade endpoint: /data/v1/get/{type}/{freq}/{cl}
#   type=C (commodity), freq=A (annual), cl=S4 (SITC Rev 4)
# Annual SITC matches the SingStat sheet's classification AND avoids the
# patchy SITC-monthly coverage we hit with CN/IN in the previous probe.
COMTRADE_URL = "https://comtradeapi.un.org/data/v1/get/C/A/S4"


# Annual probes for the dependence baseline. SITC Annual is reliably
# populated for all 10 reporters back to at least 2010; we only need 2023-2025.
HISTORICAL_PROBES = [
    ("2025",  "2025"),
    ("2024",  "2024"),
    ("2023",  "2023"),
]


def _get_with_retry(params: dict, headers: dict, max_retries: int = 5) -> "tuple[int, dict | None]":
    """GET with exponential backoff on 429 / 5xx. Returns (status_code, json_or_None)."""
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
    return 429, None  # ran out of retries


def probe_one(reporter_iso: str, reporter_name: str, reporter_code: str,
              partner_code: str, partner_label: str,
              periods: list[str], headers: dict) -> dict:
    """One Comtrade SITC Annual call (with retry/backoff). Walks through
    fallback periods until one returns data."""
    for period in periods:
        params = {
            "reporterCode": reporter_code,
            "partnerCode":  partner_code,
            "period":       period,
            "cmdCode":      PROBE_SITC_CODE,
            "flowCode":     "M",  # Imports
            "includeDesc":  "true",
        }
        status, payload = _get_with_retry(params, headers)
        if status == 429:
            return {"status": "RATE_LIMITED_AFTER_RETRIES", "period": period}
        if status != 200:
            return {"status": f"HTTP {status}", "period": period}
        rows = (payload or {}).get("data") or []
        if not rows:
            time.sleep(1.0)  # be polite between period retries
            continue
        first = rows[0]
        return {
            "status":      "OK",
            "period":      period,
            "n_rows":      len(rows),
            "trade_value": first.get("primaryValue"),
            "partner_iso": first.get("partnerISO") or first.get("partnerDesc"),
        }
    return {"status": "NO_DATA", "period": periods[-1]}


def main() -> None:
    api_key = os.environ.get("COMTRADE_API_KEY", "")
    if not api_key:
        sys.exit("COMTRADE_API_KEY not set in .env.")
    headers = {"Ocp-Apim-Subscription-Key": api_key, "Accept": "application/json"}

    print(f"Probing Comtrade SITC Rev 4 ANNUAL mode — chapter {PROBE_SITC_CODE} "
          f"(Chemicals total), Imports.")
    print(f"  Years: {[p for _, p in HISTORICAL_PROBES]}")
    print(f"  10 reporters × 2 partners × 3 years = 60 calls max, with retry+backoff.\n")

    # Just the historical samples — the actual baseline we care about.
    historical_results: dict[str, dict] = {}
    for iso, (name, code) in REGIONAL_REPORTERS.items():
        per_iso = {}
        for label, period in HISTORICAL_PROBES:
            rw = probe_one(iso, name, code, WORLD_PARTNER_CODE, "World",
                           [period], headers)
            time.sleep(1.5)   # polite gap between calls
            rs = probe_one(iso, name, code, SINGAPORE_PARTNER_CODE, "Singapore",
                           [period], headers)
            time.sleep(1.5)
            per_iso[label] = (rw, rs)
        historical_results[iso] = per_iso
        # Live one-line summary per reporter
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
    print(f"  SG share of SITC chapter {PROBE_SITC_CODE} (Chemicals) imports — annual")
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
    print("Once we have ✓s across all 10 reporters, the full ingestion pulls SITC chapters")
    print("5 (chemicals total), 51 (organics — to subtract), 54 (pharma — to subtract) annually")
    print("for all 10 reporters × (World, Singapore) partners × 3 years (2023-2025) = 180 calls.")


if __name__ == "__main__":
    main()
