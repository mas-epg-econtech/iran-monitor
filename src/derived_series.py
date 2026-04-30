"""
Derived series — values computed from other tables in the DB rather than
fetched from an external source.

Currently:
  - mas_core_inflation_mom : derived from ceic_mas_core_inflation_index
    (the level index 2024=100). MAS doesn't publish a Core Inflation MoM
    series directly — only the level and the YoY — so we compute the
    month-on-month percentage change ourselves: (level_t / level_{t-1} - 1) × 100.

  - singstat_chem_export_<iso2> : per-country time series of SG chemical
    exports to that country, projected from trade_singstat onto time_series
    so the existing chart_grid renderer can consume it without needing a
    new section type. One series per regional country (CN, IN, ID, JP, MY,
    PH, KR, TW, TH, VN). See compute_singstat_chem_export_country_series().
"""
from __future__ import annotations

import sqlite3


# 10 regional countries that get per-country chemical-export panels on the
# Regional Trade tab. ISO-2 used in the synthesised series_id so it stays in
# sync with the Regional CPI / IPI naming pattern.
REGIONAL_COUNTRIES_ISO2 = ["CN", "IN", "ID", "JP", "MY", "PH", "KR", "TW", "TH", "VN"]

# ME spotlight — SG mineral fuel suppliers we want to highlight on the
# Singapore Trade tab. Iran intentionally excluded (sanctions; SG doesn't
# import from Iran). Yemen excluded (effectively offline). The trade_singstat
# data has 6 of the 7 typically-quoted ME suppliers (no Iran rows present).
ME_SPOTLIGHT_ISO2 = ["AE", "SA", "QA", "KW", "IQ", "OM"]

# SITC codes from the SG_Annual_Imports / SG_Monthly_Imports tabs that get
# their own row on the Singapore Trade Exposure tab — chapter, 3-digit
# divisions, plus the 7-digit SingStat sub-codes that the colleagues
# specifically pulled out (likely jet fuel + LNG).
SG_IMPORT_SITC_CODES = ["SITC_3", "SITC_333", "SITC_334", "SITC_343",
                        "SITC_3346043", "SITC_3431000"]

SG_IMPORT_SITC_LABELS = {
    "SITC_3":         "Mineral Fuels (total)",
    "SITC_333":       "Crude Petroleum Oils",
    "SITC_334":       "Refined Petroleum Products",
    "SITC_343":       "Natural Gas",
    "SITC_3346043":   "Naphtha (SITC 3346043)",
    "SITC_3431000":   "LNG (SITC 3431000)",
}


def compute_mas_core_mom(conn: sqlite3.Connection) -> int:
    """Compute MAS Core Inflation MoM from the level index and upsert into time_series.

    Returns the number of rows written. Idempotent — safe to re-run after every
    ingest cycle (uses INSERT OR REPLACE on the (date, series_id) primary key).
    """
    rows = conn.execute(
        "SELECT date, value FROM time_series "
        "WHERE series_id = 'ceic_mas_core_inflation_index' AND value IS NOT NULL "
        "ORDER BY date"
    ).fetchall()
    if len(rows) < 2:
        return 0

    out_rows = []
    prev_val = None
    for date, value in rows:
        if prev_val is not None and prev_val != 0:
            mom_pct = (value / prev_val - 1) * 100
            out_rows.append((
                date, mom_pct,
                "mas_core_inflation_mom",
                "MAS Core Inflation MoM",
                "derived",
                "% MoM",
                "Monthly",
            ))
        prev_val = value

    conn.executemany(
        "INSERT OR REPLACE INTO time_series "
        "(date, value, series_id, series_name, source, unit, frequency, category) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, NULL)",
        out_rows,
    )
    conn.commit()
    return len(out_rows)


def _compute_singstat_export_country_series(
    conn: sqlite3.Connection,
    *,
    product_code: str,
    series_prefix: str,
    product_human: str,
) -> int:
    """Project trade_singstat for one product_code → per-country time_series.

    Generic version of `compute_singstat_chem_export_country_series` —
    parameterised by product_code so we can run it for both chemicals
    (SITC 5 less 51 less 54) and refined petroleum (SITC 334).

    Emits two series per country:
      <series_prefix>_annual_<iso2>   — annual observations
      <series_prefix>_monthly_<iso2>  — monthly observations

    Idempotent — wipes the matching series_ids first.
    """
    out_rows: list[tuple] = []

    for iso2 in REGIONAL_COUNTRIES_ISO2:
        rows = conn.execute(
            """
            SELECT period, value_sgd_thou, frequency, partner_display
            FROM trade_singstat
            WHERE flow = 'Exports'
              AND product_code = ?
              AND partner_iso2 = ?
            ORDER BY period
            """,
            (product_code, iso2),
        ).fetchall()
        if not rows:
            continue

        partner_display = rows[0][3] or iso2

        for period, value, freq, _disp in rows:
            if value is None:
                continue
            if freq == "Annual":
                series_id = f"{series_prefix}_annual_{iso2.lower()}"
                series_name = f"SG {product_human} exports to {partner_display} (annual)"
            elif freq == "Monthly":
                series_id = f"{series_prefix}_monthly_{iso2.lower()}"
                series_name = f"SG {product_human} exports to {partner_display} (monthly)"
            else:
                continue
            out_rows.append((
                period, float(value), series_id, series_name,
                "singstat", "SGD Thousand", freq,
            ))

    # Wipe existing derived rows so a country dropped from the regional list
    # doesn't leave orphans.
    sids_to_clear = []
    for iso2 in REGIONAL_COUNTRIES_ISO2:
        sids_to_clear.extend([
            f"{series_prefix}_annual_{iso2.lower()}",
            f"{series_prefix}_monthly_{iso2.lower()}",
        ])
    placeholders = ",".join("?" for _ in sids_to_clear)
    conn.execute(
        f"DELETE FROM time_series WHERE series_id IN ({placeholders})",
        sids_to_clear,
    )

    if not out_rows:
        conn.commit()
        return 0
    conn.executemany(
        "INSERT INTO time_series (date, value, series_id, series_name, source, unit, frequency) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        out_rows,
    )
    conn.commit()
    return len(out_rows)


def compute_singstat_chem_export_country_series(conn: sqlite3.Connection) -> int:
    """Per-country chemicals export series (SITC 5 less 51 less 54)."""
    n = _compute_singstat_export_country_series(
        conn,
        product_code="SITC_5_excl_51_54",
        series_prefix="singstat_chem_export",
        product_human="chemical",
    )
    # Also clear the legacy combined series_id from previous iterations.
    legacy = [f"singstat_chem_export_{iso2.lower()}"
              for iso2 in REGIONAL_COUNTRIES_ISO2]
    conn.execute(
        f"DELETE FROM time_series WHERE series_id IN ({','.join('?' for _ in legacy)})",
        legacy,
    )
    conn.commit()
    return n


def compute_singstat_petroleum_export_country_series(conn: sqlite3.Connection) -> int:
    """Per-country refined-petroleum (SITC 334) export series — same shape
    as the chemicals function, parallel data feed for the regional fuel
    dependence cards."""
    return _compute_singstat_export_country_series(
        conn,
        product_code="SITC_334",
        series_prefix="singstat_petroleum_export",
        product_human="refined petroleum",
    )



# ════════════════════════════════════════════════════════════════════════
# Singapore Trade tab derivations (sections 1+2 mineral fuels imports;
# sections 3+4 chemicals exports). All sourced from trade_singstat.
# ════════════════════════════════════════════════════════════════════════

def _wipe_series_prefix(conn: sqlite3.Connection, prefix: str) -> int:
    """Delete every time_series row whose series_id starts with `prefix`.
    Used at the top of each derivation to avoid stale rows from prior runs."""
    return conn.execute(
        "DELETE FROM time_series WHERE series_id LIKE ?",
        (f"{prefix}%",),
    ).rowcount


def compute_sg_me_import_shares(conn: sqlite3.Connection) -> int:
    """Annual ME-spotlight shares of SG mineral fuel imports — per (SITC, ME
    country) PLUS an "Others" residual so the stacked-bar columns add to 100%.

    For each (SITC ∈ SG_IMPORT_SITC_CODES) × year:
      ME share per country = ME_country_value / sum_all_named_partners * 100
      Others share         = 100 - sum(ME shares)   [includes long-tail
                              non-ME partners + the residual we miss because
                              the SingStat sheet's "TOTAL FOR OTHER COUNTRIES"
                              row is filtered out at ingest]

    Output series:
      `sg_imp_share_<sitc_lower>_<iso2_lower>`  for each ME country
      `sg_imp_share_<sitc_lower>_others`        for the residual

    Used by the LEFT chart of each SITC row on the Trade Exposure tab.
    """
    _wipe_series_prefix(conn, "sg_imp_share_")
    out_rows = []
    years = [2023, 2024, 2025]

    for sitc_code in SG_IMPORT_SITC_CODES:
        for year in years:
            period = f"{year}-12-31"
            r = conn.execute(
                "SELECT SUM(value_sgd_thou) FROM trade_singstat "
                "WHERE flow='Imports' AND product_code=? AND frequency='Annual' "
                "AND period=?",
                (sitc_code, period),
            ).fetchone()
            total = r[0] if r and r[0] else None
            if not total or total <= 0:
                continue

            sum_me_share = 0.0
            for iso2 in ME_SPOTLIGHT_ISO2:
                pr = conn.execute(
                    "SELECT value_sgd_thou FROM trade_singstat "
                    "WHERE flow='Imports' AND product_code=? AND frequency='Annual' "
                    "AND period=? AND partner_iso2=?",
                    (sitc_code, period, iso2),
                ).fetchone()
                value = float(pr[0]) if pr and pr[0] is not None else 0.0
                share_pct = value / float(total) * 100.0
                sum_me_share += share_pct
                # Always emit a row (even if 0) so the chart can show every
                # ME country in the legend with a colored segment, even if
                # the segment is invisibly small.
                series_id = f"sg_imp_share_{sitc_code.lower()}_{iso2.lower()}"
                out_rows.append((
                    period, share_pct, series_id,
                    f"SG {SG_IMPORT_SITC_LABELS.get(sitc_code, sitc_code)} imports — share from {iso2}",
                    "singstat", "% share", "Annual",
                ))

            # Others residual — everything that isn't an ME-spotlight partner.
            others_share = max(0.0, 100.0 - sum_me_share)
            series_id = f"sg_imp_share_{sitc_code.lower()}_others"
            out_rows.append((
                period, others_share, series_id,
                f"SG {SG_IMPORT_SITC_LABELS.get(sitc_code, sitc_code)} imports — share from non-ME partners",
                "singstat", "% share", "Annual",
            ))

    if out_rows:
        conn.executemany(
            "INSERT OR REPLACE INTO time_series "
            "(date, value, series_id, series_name, source, unit, frequency, category) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, NULL)",
            out_rows,
        )
        conn.commit()
    return len(out_rows)


def _stash_benchmark(conn: sqlite3.Connection, series_id: str, monthly_avg: float) -> None:
    """Persist a chart's 2023-25 monthly benchmark in the metadata table so
    the renderer can pick it up at build time."""
    import json
    existing = conn.execute(
        "SELECT value FROM metadata WHERE key = 'trade_chart_benchmarks'"
    ).fetchone()
    obj = json.loads(existing[0]) if existing else {}
    obj[series_id] = monthly_avg
    conn.execute(
        "INSERT INTO metadata (key, value) VALUES ('trade_chart_benchmarks', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (json.dumps(obj),),
    )


def compute_sg_import_monthly_aggregates(conn: sqlite3.Connection) -> int:
    """Per-partner monthly SG mineral fuel imports for each SITC code.

    For each (SITC ∈ SG_IMPORT_SITC_CODES) × month:
      - one series per ME-spotlight country with that month's value
      - one Others series = monthly_total - sum_ME

    Output series:
      sg_imp_monthly_<sitc_lower>_<iso2_lower>   per ME country
      sg_imp_monthly_<sitc_lower>_others          residual non-ME partners

    Used by the RIGHT chart of each SITC row on the Trade Exposure tab —
    stacked monthly bars where each bar's total height equals SG's total
    monthly imports of that SITC.

    Also stashes 2023-25 monthly-average benchmark values for each chart's
    horizontal reference line (per SITC, only the chart-total benchmark
    is needed since the dashed line cuts across the whole stack at the
    historical mean).
    """
    _wipe_series_prefix(conn, "sg_imp_monthly_")
    out_rows = []

    for sitc_code in SG_IMPORT_SITC_CODES:
        sitc_label = SG_IMPORT_SITC_LABELS.get(sitc_code, sitc_code)

        # Per-month: total across all partners (denominator + benchmark base)
        monthly_totals: dict[str, float] = {}
        for r in conn.execute(
            "SELECT period, SUM(value_sgd_thou) FROM trade_singstat "
            "WHERE flow='Imports' AND product_code=? AND frequency='Monthly' "
            "GROUP BY period",
            (sitc_code,),
        ).fetchall():
            if r[1] is not None:
                monthly_totals[r[0]] = float(r[1])

        if not monthly_totals:
            continue

        # Per-ME-country monthly values
        for iso2 in ME_SPOTLIGHT_ISO2:
            for r in conn.execute(
                "SELECT period, value_sgd_thou FROM trade_singstat "
                "WHERE flow='Imports' AND product_code=? AND frequency='Monthly' "
                "AND partner_iso2=? ORDER BY period",
                (sitc_code, iso2),
            ).fetchall():
                period, value = r[0], r[1]
                if value is None:
                    continue
                series_id = f"sg_imp_monthly_{sitc_code.lower()}_{iso2.lower()}"
                out_rows.append((
                    period, float(value), series_id,
                    f"SG {sitc_label} imports from {iso2}",
                    "singstat", "SGD Thousand", "Monthly",
                ))

        # Per-month Others = total - sum of ME values that month
        for period, total in monthly_totals.items():
            r = conn.execute(
                f"SELECT SUM(value_sgd_thou) FROM trade_singstat "
                f"WHERE flow='Imports' AND product_code=? AND frequency='Monthly' "
                f"AND period=? AND partner_iso2 IN ({','.join('?' for _ in ME_SPOTLIGHT_ISO2)})",
                (sitc_code, period, *ME_SPOTLIGHT_ISO2),
            ).fetchone()
            me_sum = float(r[0]) if r and r[0] is not None else 0.0
            others_value = max(0.0, total - me_sum)
            series_id = f"sg_imp_monthly_{sitc_code.lower()}_others"
            out_rows.append((
                period, others_value, series_id,
                f"SG {sitc_label} imports — non-ME partners",
                "singstat", "SGD Thousand", "Monthly",
            ))

        # 2023-25 monthly-average benchmark for THIS SITC's chart total.
        # Stored against the Others series_id (an arbitrary but stable key
        # the chart's right-card layout will pick up via auto-lookup) — the
        # value represents the historical avg total monthly import level so
        # the dashed line cuts across the whole stack at that level.
        annual_totals = [
            row[1] for row in conn.execute(
                "SELECT period, SUM(value_sgd_thou) FROM trade_singstat "
                "WHERE flow='Imports' AND product_code=? AND frequency='Annual' GROUP BY period",
                (sitc_code,),
            ).fetchall() if row[1] is not None
        ]
        if annual_totals:
            avg_monthly = sum(annual_totals) / len(annual_totals) / 12.0
            _stash_benchmark(conn, f"sg_imp_monthly_{sitc_code.lower()}_others", avg_monthly)

    if out_rows:
        conn.executemany(
            "INSERT OR REPLACE INTO time_series "
            "(date, value, series_id, series_name, source, unit, frequency, category) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, NULL)",
            out_rows,
        )
    conn.commit()
    return len(out_rows)


def compute_sg_chem_export_regional_shares(conn: sqlite3.Connection) -> int:
    """Annual regional shares of SG industrial-chemical exports
    (SITC 5 less 51 less 54).

    Output series: sg_chem_export_share_<iso2_lower>, annual data points.
    Used by Section 3 of the Singapore Trade tab.
    """
    _wipe_series_prefix(conn, "sg_chem_export_share_")
    out_rows = []
    years = [2023, 2024, 2025]

    for year in years:
        period = f"{year}-12-31"
        r = conn.execute(
            "SELECT SUM(value_sgd_thou) FROM trade_singstat "
            "WHERE flow='Exports' AND product_code='SITC_5_excl_51_54' "
            "AND frequency='Annual' AND period=?",
            (period,),
        ).fetchone()
        total = r[0] if r and r[0] else None
        if not total or total <= 0:
            continue
        for iso2 in REGIONAL_COUNTRIES_ISO2:
            pr = conn.execute(
                "SELECT value_sgd_thou, partner_display FROM trade_singstat "
                "WHERE flow='Exports' AND product_code='SITC_5_excl_51_54' "
                "AND frequency='Annual' AND period=? AND partner_iso2=?",
                (period, iso2),
            ).fetchone()
            if not pr or pr[0] is None:
                continue
            share_pct = float(pr[0]) / float(total) * 100.0
            series_id = f"sg_chem_export_share_{iso2.lower()}"
            series_name = f"{pr[1]} share of SG industrial-chemical exports"
            out_rows.append((
                period, share_pct, series_id, series_name,
                "singstat", "% share", "Annual",
            ))

    if out_rows:
        conn.executemany(
            "INSERT OR REPLACE INTO time_series "
            "(date, value, series_id, series_name, source, unit, frequency, category) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, NULL)",
            out_rows,
        )
        conn.commit()
    return len(out_rows)


def compute_sg_chem_export_monthly_aggregates(conn: sqlite3.Connection) -> int:
    """Monthly aggregate SG industrial-chemical exports — Total + Regional aggregate.

    Output series:
      sg_chem_export_monthly_total     — Total monthly across all destinations
      sg_chem_export_monthly_regional  — Sum of 10 regional countries
      sg_chem_export_monthly_others    — Total minus Regional (non-regional residual)

    Plus 2023-25 monthly-average benchmarks in metadata.
    Used by Section 4 of the Singapore Trade tab.
    """
    _wipe_series_prefix(conn, "sg_chem_export_monthly_")
    out_rows = []

    # Build {period: total} and {period: regional_sum} so we can also emit
    # an Others series (= total - regional) for the stacked levels chart.
    totals: dict[str, float] = {}
    regional: dict[str, float] = {}

    for r in conn.execute(
        "SELECT period, SUM(value_sgd_thou) FROM trade_singstat "
        "WHERE flow='Exports' AND product_code='SITC_5_excl_51_54' "
        "AND frequency='Monthly' GROUP BY period ORDER BY period"
    ).fetchall():
        if r[1] is not None:
            totals[r[0]] = float(r[1])
            out_rows.append((
                r[0], float(r[1]),
                "sg_chem_export_monthly_total",
                "SG industrial-chemical exports — Total (all destinations)",
                "singstat", "SGD Thousand", "Monthly",
            ))

    placeholders = ",".join("?" for _ in REGIONAL_COUNTRIES_ISO2)
    for r in conn.execute(
        f"SELECT period, SUM(value_sgd_thou) FROM trade_singstat "
        f"WHERE flow='Exports' AND product_code='SITC_5_excl_51_54' "
        f"AND frequency='Monthly' AND partner_iso2 IN ({placeholders}) "
        f"GROUP BY period ORDER BY period",
        REGIONAL_COUNTRIES_ISO2,
    ).fetchall():
        if r[1] is not None:
            regional[r[0]] = float(r[1])
            out_rows.append((
                r[0], float(r[1]),
                "sg_chem_export_monthly_regional",
                "SG industrial-chemical exports — Regional aggregate (10 Asian economies)",
                "singstat", "SGD Thousand", "Monthly",
            ))

    # Others = total - regional. Emit per-period so the stacked monthly
    # levels chart sums to the all-destinations total.
    for period, total in totals.items():
        others = total - regional.get(period, 0.0)
        out_rows.append((
            period, max(others, 0.0),
            "sg_chem_export_monthly_others",
            "SG industrial-chemical exports — Other destinations (non-regional)",
            "singstat", "SGD Thousand", "Monthly",
        ))

    if out_rows:
        conn.executemany(
            "INSERT OR REPLACE INTO time_series "
            "(date, value, series_id, series_name, source, unit, frequency, category) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, NULL)",
            out_rows,
        )

    for series_id, where_partners in (
        ("sg_chem_export_monthly_total",    None),
        ("sg_chem_export_monthly_regional", REGIONAL_COUNTRIES_ISO2),
    ):
        if where_partners:
            ph = ",".join("?" for _ in where_partners)
            sql = (
                f"SELECT period, SUM(value_sgd_thou) FROM trade_singstat "
                f"WHERE flow='Exports' AND product_code='SITC_5_excl_51_54' "
                f"AND frequency='Annual' AND partner_iso2 IN ({ph}) GROUP BY period"
            )
            params = where_partners
        else:
            sql = (
                "SELECT period, SUM(value_sgd_thou) FROM trade_singstat "
                "WHERE flow='Exports' AND product_code='SITC_5_excl_51_54' "
                "AND frequency='Annual' GROUP BY period"
            )
            params = ()
        annuals = [row[1] for row in conn.execute(sql, params).fetchall() if row[1] is not None]
        if annuals:
            _stash_benchmark(conn, series_id, sum(annuals) / len(annuals) / 12.0)

    # ── Stacked monthly levels chart benchmark ───────────────────────────
    # The combined-card export levels chart sums 10 per-country series +
    # Others; the visually meaningful benchmark on a stacked chart is the
    # 2023-25 monthly average of the TOTAL exports. The renderer's auto-
    # attach loop iterates the chart's series_ids and uses the first one
    # with a stashed benchmark — so we duplicate the *total* benchmark
    # under each constituent series_id of the stacked levels chart so it
    # gets picked up regardless of iteration order.
    annual_totals = [
        row[1] for row in conn.execute(
            "SELECT period, SUM(value_sgd_thou) FROM trade_singstat "
            "WHERE flow='Exports' AND product_code='SITC_5_excl_51_54' "
            "AND frequency='Annual' GROUP BY period"
        ).fetchall() if row[1] is not None
    ]
    if annual_totals:
        total_monthly_avg = sum(annual_totals) / len(annual_totals) / 12.0
        # Per-country monthly export series (10 regional countries) + Others.
        for iso2 in REGIONAL_COUNTRIES_ISO2:
            _stash_benchmark(
                conn, f"singstat_chem_export_monthly_{iso2.lower()}",
                total_monthly_avg,
            )
        _stash_benchmark(conn, "sg_chem_export_monthly_others", total_monthly_avg)

    conn.commit()
    return len(out_rows)


# ════════════════════════════════════════════════════════════════════════
# Regional Trade Exposure tab — per-country chemical-import dependence on
# Singapore. Mirrors the SG-side mineral-fuel cards, but with SG as the
# spotlight partner (instead of the 6 ME suppliers).
# ════════════════════════════════════════════════════════════════════════

# Comtrade ISO3 for Singapore (the source of the chemical exports).
_COMTRADE_SG_ISO3 = "SGP"


def compute_regional_chem_share_from_sg(conn: sqlite3.Connection) -> int:
    """For each of the 10 regional countries, compute SG's % share of their
    industrial chemical imports — annually for the years present in
    `trade_comtrade_dep`. Output series:

      regional_chem_share_from_sg_<iso2_lower>

    "Industrial chemicals" = SITC 5 less SITC 51 (organics) less SITC 54
    (pharmaceuticals) — the same framing used by the SG-side cards.

    For each (reporter, year):
        sg_value     = sum SG-partner row of (5) − (51) − (54)
        world_value  = sum across all partners of (5) − (51) − (54)
        share_pct    = sg_value / world_value × 100

    Idempotent — wipes regional_chem_share_from_sg_* before re-emitting.
    Returns the number of rows written (silent zero if `trade_comtrade_dep`
    is empty, which is the case before the Comtrade ingest has run).
    """
    _wipe_series_prefix(conn, "regional_chem_share_from_sg_")

    # Bail early if the Comtrade table doesn't exist or is empty — keeps
    # the dashboard build working before the ingest has run.
    try:
        n_rows = conn.execute(
            "SELECT COUNT(*) FROM trade_comtrade_dep"
        ).fetchone()[0]
    except sqlite3.OperationalError:
        return 0
    if n_rows == 0:
        return 0

    out_rows = []
    for iso2 in REGIONAL_COUNTRIES_ISO2:
        # Find the years for which this reporter has data
        years = [r[0] for r in conn.execute(
            "SELECT DISTINCT period FROM trade_comtrade_dep "
            "WHERE reporter_iso2=? ORDER BY period",
            (iso2,),
        ).fetchall()]
        if not years:
            continue

        for period in years:
            # Industrial chem total per partner = SITC 5 - 51 - 54.
            # Pull all partners for these 3 codes and reduce in Python so
            # we can compute (5 - 51 - 54) per partner cleanly.
            #
            # IMPORTANT: trade_comtrade_dep stores BOTH a `W00` row (the
            # Comtrade-supplied World aggregate) AND rows for every
            # individual partner (whose values sum to the same world
            # total). We use the W00 row directly as the denominator —
            # don't sum across all partners or we'd double-count.
            rows = conn.execute(
                "SELECT partner_iso3, sitc_code, value_usd FROM trade_comtrade_dep "
                "WHERE reporter_iso2=? AND period=? AND sitc_code IN ('5','51','54')",
                (iso2, period),
            ).fetchall()
            if not rows:
                continue

            # partner_iso3 -> {sitc_code -> value}
            by_partner: dict[str, dict[str, float]] = {}
            for partner, sitc, val in rows:
                by_partner.setdefault(partner, {})[sitc] = float(val or 0)

            def _industrial_for(partner_iso3: str) -> float:
                """SITC 5 less SITC 51 less SITC 54 for one partner. Floored
                at zero in case of reporting noise where 51+54 > 5."""
                codes = by_partner.get(partner_iso3, {})
                return max(
                    codes.get("5", 0.0)
                    - codes.get("51", 0.0)
                    - codes.get("54", 0.0),
                    0.0,
                )

            world_val = _industrial_for("W00")   # use the aggregate row directly
            sg_val    = _industrial_for(_COMTRADE_SG_ISO3)
            if world_val <= 0:
                continue
            share_pct = sg_val / world_val * 100.0

            out_rows.append((
                period, share_pct,
                f"regional_chem_share_from_sg_{iso2.lower()}",
                f"SG share of {iso2}'s industrial-chemical imports",
                "comtrade", "% share", "Annual",
            ))

    if out_rows:
        conn.executemany(
            "INSERT OR REPLACE INTO time_series "
            "(date, value, series_id, series_name, source, unit, frequency, category) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, NULL)",
            out_rows,
        )
        conn.commit()
    return len(out_rows)


def compute_regional_fuel_share_from_sg(conn: sqlite3.Connection) -> int:
    """For each of the 10 regional countries, compute SG's % share of their
    refined petroleum imports (SITC 334) — annually for the years present
    in `trade_comtrade_dep`. Output series:

      regional_fuel_share_from_sg_<iso2_lower>

    Simpler than the chemicals analogue (no subtraction): just SG's SITC 334
    value over World's SITC 334 value. Uses the W00 (World) row directly
    as the denominator — see compute_regional_chem_share_from_sg() for the
    same caveat.

    Returns the number of rows written.
    """
    _wipe_series_prefix(conn, "regional_fuel_share_from_sg_")

    try:
        n_rows = conn.execute("SELECT COUNT(*) FROM trade_comtrade_dep").fetchone()[0]
    except sqlite3.OperationalError:
        return 0
    if n_rows == 0:
        return 0

    out_rows = []
    for iso2 in REGIONAL_COUNTRIES_ISO2:
        years = [r[0] for r in conn.execute(
            "SELECT DISTINCT period FROM trade_comtrade_dep "
            "WHERE reporter_iso2=? ORDER BY period",
            (iso2,),
        ).fetchall()]
        if not years:
            continue

        for period in years:
            world_row = conn.execute(
                "SELECT value_usd FROM trade_comtrade_dep "
                "WHERE reporter_iso2=? AND period=? AND sitc_code='334' AND partner_iso3='W00'",
                (iso2, period),
            ).fetchone()
            sg_row = conn.execute(
                "SELECT value_usd FROM trade_comtrade_dep "
                "WHERE reporter_iso2=? AND period=? AND sitc_code='334' AND partner_iso3=?",
                (iso2, period, _COMTRADE_SG_ISO3),
            ).fetchone()
            if not world_row or not world_row[0]:
                continue
            world_val = float(world_row[0])
            sg_val    = float(sg_row[0]) if sg_row and sg_row[0] is not None else 0.0
            share_pct = sg_val / world_val * 100.0
            out_rows.append((
                period, share_pct,
                f"regional_fuel_share_from_sg_{iso2.lower()}",
                f"SG share of {iso2}'s refined petroleum (SITC 334) imports",
                "comtrade", "% share", "Annual",
            ))

    if out_rows:
        conn.executemany(
            "INSERT OR REPLACE INTO time_series "
            "(date, value, series_id, series_name, source, unit, frequency, category) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, NULL)",
            out_rows,
        )
        conn.commit()
    return len(out_rows)


def compute_regional_chem_levels(conn: sqlite3.Connection) -> int:
    """Per-country alias series of `singstat_chem_export_monthly_<iso2>`
    used by the Regional Trade tab's per-country dependence cards.

    Why an alias and not just point at the existing series: the SG-side
    combined card already stashes a *total* benchmark on each
    `singstat_chem_export_monthly_<iso2>` series so its stacked chart can
    auto-attach. The regional cards need a *per-country* benchmark on the
    same logical data, so we copy the data under a new series_id and stash
    a per-country benchmark on the alias — keeping the two cards' benchmark
    semantics independent.

    Output series:
      regional_chem_imports_from_sg_<iso2>  — identical monthly values to
        `singstat_chem_export_monthly_<iso2>`, with per-country 2023-24
        monthly-avg benchmark stashed on the same key.

    Returns the number of (iso2, period) rows written.
    """
    _wipe_series_prefix(conn, "regional_chem_imports_from_sg_")
    out_rows = []
    BENCHMARK_YEARS = ("2023-12-31", "2024-12-31")

    for iso2 in REGIONAL_COUNTRIES_ISO2:
        # Copy monthly observations from the existing series.
        for r in conn.execute(
            "SELECT date, value FROM time_series "
            "WHERE series_id=? ORDER BY date",
            (f"singstat_chem_export_monthly_{iso2.lower()}",),
        ).fetchall():
            out_rows.append((
                r[0], float(r[1]),
                f"regional_chem_imports_from_sg_{iso2.lower()}",
                f"{iso2} monthly chemical imports from SG (alias for regional cards)",
                "singstat", "SGD Thousand", "Monthly",
            ))

        # 2023-24 monthly-avg benchmark — per country, from SingStat annual
        # data (same source as the levels series so the bars and the
        # benchmark line are on the same scale).
        annuals = [
            row[0] for row in conn.execute(
                "SELECT value_sgd_thou FROM trade_singstat "
                "WHERE flow='Exports' AND product_code='SITC_5_excl_51_54' "
                "AND frequency='Annual' AND partner_iso2=? AND period IN (?, ?)",
                (iso2, *BENCHMARK_YEARS),
            ).fetchall() if row[0] is not None
        ]
        if annuals:
            _stash_benchmark(
                conn, f"regional_chem_imports_from_sg_{iso2.lower()}",
                sum(annuals) / len(annuals) / 12.0,
            )

    if out_rows:
        conn.executemany(
            "INSERT OR REPLACE INTO time_series "
            "(date, value, series_id, series_name, source, unit, frequency, category) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, NULL)",
            out_rows,
        )
        conn.commit()
    return len(out_rows)


def compute_regional_fuel_levels(conn: sqlite3.Connection) -> int:
    """Per-country alias of `singstat_petroleum_export_monthly_<iso2>` —
    same shape as compute_regional_chem_levels but for SITC 334 refined
    petroleum. Stashes a per-country 2023-24 monthly-avg benchmark so the
    Regional Trade tab's monthly cards have a dashed reference line.

    Output: regional_fuel_imports_from_sg_<iso2_lower>
    """
    _wipe_series_prefix(conn, "regional_fuel_imports_from_sg_")
    out_rows = []
    BENCHMARK_YEARS = ("2023-12-31", "2024-12-31")

    for iso2 in REGIONAL_COUNTRIES_ISO2:
        for r in conn.execute(
            "SELECT date, value FROM time_series "
            "WHERE series_id=? ORDER BY date",
            (f"singstat_petroleum_export_monthly_{iso2.lower()}",),
        ).fetchall():
            out_rows.append((
                r[0], float(r[1]),
                f"regional_fuel_imports_from_sg_{iso2.lower()}",
                f"{iso2} monthly refined-petroleum imports from SG (alias)",
                "singstat", "SGD Thousand", "Monthly",
            ))

        # Benchmark from SingStat 2023-24 annual data for this country/SITC 334
        annuals = [
            row[0] for row in conn.execute(
                "SELECT value_sgd_thou FROM trade_singstat "
                "WHERE flow='Exports' AND product_code='SITC_334' "
                "AND frequency='Annual' AND partner_iso2=? AND period IN (?, ?)",
                (iso2, *BENCHMARK_YEARS),
            ).fetchall() if row[0] is not None
        ]
        if annuals:
            _stash_benchmark(
                conn, f"regional_fuel_imports_from_sg_{iso2.lower()}",
                sum(annuals) / len(annuals) / 12.0,
            )

    if out_rows:
        conn.executemany(
            "INSERT OR REPLACE INTO time_series "
            "(date, value, series_id, series_name, source, unit, frequency, category) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, NULL)",
            out_rows,
        )
        conn.commit()
    return len(out_rows)


# ════════════════════════════════════════════════════════════════════════
# Singapore Shipping tab — projects the shipping nowcast JSON into
# time_series so the chart_grid renderer can consume it natively.
# ════════════════════════════════════════════════════════════════════════

NOWCAST_JSON_PATH = "data/shipping/nowcast_results_s13.json"

# Stable series_ids the dashboard's page_layouts.py references.
# Each pair = (actual_id, counterfactual_id) for the same metric.
NOWCAST_SERIES_NAME = "Actual"
NOWCAST_CF_NAME     = "Counterfactual (Primary)"


def _stream_nowcast_series(payload: dict, key: str) -> tuple[list[str], list[float], list[float]] | None:
    """Pull (dates, actual, counterfactual_primary) for one location|metric key.
    Returns None if the key is missing."""
    entry = payload.get(key)
    if not entry:
        return None
    return entry["dates"], entry["actual"], entry["counterfactual_primary"]


def _emit_nowcast_pair(out_rows: list, dates: list[str], actual: list[float],
                       cf: list[float], series_id_actual: str, series_id_cf: str,
                       metric_label: str) -> None:
    """Emit two series_id streams (actual + counterfactual) into out_rows.
    Unit is inferred from the series_id ('_tonnage_' → tonnage, else calls)."""
    unit = "Metric tonnes" if "_tonnage_" in series_id_actual else "Vessel calls"
    for d, a, c in zip(dates, actual, cf):
        if a is not None:
            out_rows.append((d, float(a), series_id_actual,
                             f"{metric_label} — Actual",
                             "portwatch_nowcast", unit, "Weekly"))
        if c is not None:
            out_rows.append((d, float(c), series_id_cf,
                             f"{metric_label} — Counterfactual (Primary)",
                             "portwatch_nowcast", unit, "Weekly"))


def _zip_sum(a: list[float], b: list[float]) -> list[float]:
    """Element-wise sum, treating None as 0; if BOTH are None at idx, result is None."""
    out = []
    for x, y in zip(a, b):
        if x is None and y is None:
            out.append(None)
        else:
            out.append((x or 0) + (y or 0))
    return out


# ── Per-country shipping nowcast generator ───────────────────────────────
# Used both by the Singapore Shipping tab and the Regional Shipping tab.
# Each country gets the same 14 series (7 actual/CF pairs):
#   nowcast_<iso2>_total_calls_actual / _cf      (sum of 5 VTs)
#   nowcast_<iso2>_tanker_calls_actual / _cf
#   nowcast_<iso2>_tanker_imp_tonnage_actual / _cf   (un-suffixed = tanker tonnage)
#   nowcast_<iso2>_tanker_exp_tonnage_actual / _cf
#   nowcast_<iso2>_container_calls_actual / _cf
#   nowcast_<iso2>_container_imp_tonnage_actual / _cf
#   nowcast_<iso2>_container_exp_tonnage_actual / _cf

# Iran Monitor's regional country roster (for the Regional Shipping tab).
# ISO-2 codes match REGIONAL_COUNTRIES_ISO2 above (Taiwan dropped because the
# nowcast JSON does not carry country-level Taiwan series).
REGIONAL_SHIPPING_COUNTRIES = [
    # (iso2_lc, country_display, country_slug, country_label)
    ("cn", "China",       "china",       "China"),
    ("in", "India",       "india",       "India"),
    ("id", "Indonesia",   "indonesia",   "Indonesia"),
    ("jp", "Japan",       "japan",       "Japan"),
    ("kr", "Korea",       "korea",       "South Korea"),
    ("my", "Malaysia",    "malaysia",    "Malaysia"),
    ("ph", "Philippines", "philippines", "Philippines"),
    ("th", "Thailand",    "thailand",    "Thailand"),
    ("vn", "Vietnam",     "vietnam",     "Vietnam"),
]


def _emit_country_shipping_series(
    payload: dict, out_rows: list,
    iso2: str, country_display: str, country_slug: str, country_label: str,
) -> None:
    """Emit the 7 actual/CF pairs of nowcast series for one country.

    Mirrors `compute_singapore_shipping_nowcast`'s SG block exactly, but
    parameterised so we can run it across all 10 countries (Singapore + the
    9 regional roster countries) from a single code path.

    `iso2`            — lowercase ISO-2 code, used as the series_id prefix
                        (`nowcast_<iso2>_*`)
    `country_display` — capitalisation used in the JSON key (e.g. "Singapore")
    `country_slug`    — lowercase form used in the JSON metric (e.g. "singapore")
    `country_label`   — human-readable label for the metric_label / friendly
                        text on the chart (e.g. "South Korea")
    """
    # Per-vessel-type series (tanker + container × calls/imp_tonnage/exp_tonnage).
    # Tanker tonnage uses the un-suffixed key — that's how the upstream
    # nowcast pipeline emits it (nowcast_pipeline.py:1826 short-circuits the
    # `_<vt>_` infix for tanker). The same convention applies for every
    # country, not just Singapore.
    for vtype, vlabel in (("tanker", "Tanker"), ("container", "Container")):
        if vtype == "tanker":
            imp_tonnage_key = f"COUNTRY:{country_display} Imports|country:{country_slug}_imports_tonnage"
            exp_tonnage_key = f"COUNTRY:{country_display} Exports|country:{country_slug}_exports_tonnage"
        else:
            imp_tonnage_key = f"COUNTRY:{country_display} Imports|country:{country_slug}_imports_{vtype}_tonnage"
            exp_tonnage_key = f"COUNTRY:{country_display} Exports|country:{country_slug}_exports_{vtype}_tonnage"

        calls = _stream_nowcast_series(
            payload, f"COUNTRY:{country_display} Exports|country:{country_slug}_exports_{vtype}_calls"
        )
        imp_tonnage = _stream_nowcast_series(payload, imp_tonnage_key)
        exp_tonnage = _stream_nowcast_series(payload, exp_tonnage_key)

        if calls:
            d, a, c = calls
            _emit_nowcast_pair(out_rows, d, a, c,
                f"nowcast_{iso2}_{vtype}_calls_actual",
                f"nowcast_{iso2}_{vtype}_calls_cf",
                f"{country_label} {vlabel} port calls")
        if imp_tonnage:
            d, a, c = imp_tonnage
            _emit_nowcast_pair(out_rows, d, a, c,
                f"nowcast_{iso2}_{vtype}_imp_tonnage_actual",
                f"nowcast_{iso2}_{vtype}_imp_tonnage_cf",
                f"{country_label} {vlabel} import tonnage")
        if exp_tonnage:
            d, a, c = exp_tonnage
            _emit_nowcast_pair(out_rows, d, a, c,
                f"nowcast_{iso2}_{vtype}_exp_tonnage_actual",
                f"nowcast_{iso2}_{vtype}_exp_tonnage_cf",
                f"{country_label} {vlabel} export tonnage")

    # Country overview — sum of per-VT actuals/CFs across the 5 displayed
    # vessel types (tanker, container, dry_bulk, general_cargo, roro).
    # See compute_singapore_shipping_nowcast() docstring for why we don't
    # use the upstream `total_calls` key directly.
    OVERVIEW_VTYPES = ["tanker", "container", "dry_bulk", "general_cargo", "roro"]
    ov_dates = None
    ov_a = None
    ov_c = None
    for vt in OVERVIEW_VTYPES:
        s = _stream_nowcast_series(
            payload, f"COUNTRY:{country_display} Exports|country:{country_slug}_exports_{vt}_calls"
        )
        if not s:
            continue
        d, a, c = s
        if ov_dates is None:
            ov_dates = d
            ov_a = list(a)
            ov_c = list(c)
        else:
            if d != ov_dates:
                continue
            ov_a = _zip_sum(ov_a, a)
            ov_c = _zip_sum(ov_c, c)
    if ov_dates is not None:
        _emit_nowcast_pair(
            out_rows, ov_dates, ov_a, ov_c,
            f"nowcast_{iso2}_total_calls_actual",
            f"nowcast_{iso2}_total_calls_cf",
            f"{country_label} total port calls (sum of 5 vessel types)",
        )


# ════════════════════════════════════════════════════════════════════════
# Regional Financial Markets — indexed FX (rebased to 100 at a reference
# date) so currencies with wildly different magnitudes (MYR ~4 vs VND
# ~25,000) can share a single chart. Mirrors the convention used by the
# stand-alone markets_dashboard.html.
# ════════════════════════════════════════════════════════════════════════

# Reference date for FX rebasing. Pre-war (war started 2026-02-28) but
# late enough that all currencies have data points around it. Each
# currency's index value = (raw / raw_at_ref) × 100, so a 5% currency
# weakening shows up as 105 (more rupiah/yen needed per USD).
FX_INDEX_REFERENCE_DATE = "2026-01-01"

# FX series IDs whose indexed counterpart we'll emit. The output series_id
# is `fx_indexed_<lower>` (e.g. `fx_indexed_idr`).
FX_INDEX_SOURCES = ["IDR", "MYR", "PHP", "THB", "VND", "JPY", "CNY"]


def compute_fx_indexed(conn: sqlite3.Connection) -> int:
    """Re-base each FX series to 100 at FX_INDEX_REFERENCE_DATE so multiple
    currencies with disparate magnitudes can share a chart.

    Output series_ids: fx_indexed_<lower-iso>. Each value = raw / raw_ref × 100.
    Higher number = more local currency per USD = local currency weaker.

    Returns total rows written across all FX series. Silently skips a
    currency that has no observation at-or-after the reference date.
    """
    _wipe_series_prefix(conn, "fx_indexed_")
    out_rows = []

    for sid in FX_INDEX_SOURCES:
        # Find the raw value AT the reference date — fall through to the
        # nearest later observation if there's a weekend gap.
        ref_row = conn.execute(
            "SELECT date, value FROM time_series "
            "WHERE series_id=? AND date >= ? "
            "ORDER BY date ASC LIMIT 1",
            (sid, FX_INDEX_REFERENCE_DATE),
        ).fetchone()
        if not ref_row or not ref_row[1]:
            continue
        ref_value = float(ref_row[1])

        for r in conn.execute(
            "SELECT date, value FROM time_series WHERE series_id=? ORDER BY date",
            (sid,),
        ).fetchall():
            if r[1] is None:
                continue
            indexed = float(r[1]) / ref_value * 100.0
            out_rows.append((
                r[0], indexed,
                f"fx_indexed_{sid.lower()}",
                f"{sid} (indexed, {FX_INDEX_REFERENCE_DATE}=100)",
                "derived:fx_index",
                "Index (per-USD, base=100)",
                "Daily",
            ))

    if out_rows:
        conn.executemany(
            "INSERT OR REPLACE INTO time_series "
            "(date, value, series_id, series_name, source, unit, frequency, category) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, NULL)",
            out_rows,
        )
        conn.commit()
    return len(out_rows)


def compute_rubber_tsr20_usc(conn: sqlite3.Connection) -> int:
    """Convert Bangkok STR 20 rubber price from THB/kg to USc/kg using
    daily THB-per-USD FX. STR 20 (Standard Thai Rubber 20) ≡ TSR 20
    (Technically Specified Rubber 20) — same physical Grade 20 spec,
    different naming convention.

    Inputs (must already be in time_series):
        rubber_str20_thb  — CEIC source 37594201, THB/kg
        THB               — yfinance THB=X, "per USD" (i.e., THB per 1 USD)

    Output:
        RUBBER_TSR20      — derived USc/kg (the user-facing series on the
                            commodity card). Keeps the original ID so
                            page_layouts.py doesn't need to change.

    Math: USc/kg = (THB/kg) ÷ (THB/USD) × 100 USc/USD.

    For each rubber date, uses that date's THB rate, falling back to the
    most recent prior FX observation (FX-on-weekends fallback). Returns
    rows written.
    """
    # Wipe any existing USc series — derivation is idempotent
    conn.execute("DELETE FROM time_series WHERE series_id='RUBBER_TSR20'")

    rubber_thb = conn.execute(
        "SELECT date, value FROM time_series WHERE series_id='rubber_str20_thb' ORDER BY date"
    ).fetchall()
    if not rubber_thb:
        return 0

    fx_rows = conn.execute(
        "SELECT date, value FROM time_series WHERE series_id='THB' ORDER BY date"
    ).fetchall()
    if not fx_rows:
        return 0

    # Pre-sort FX dates so we can binary-search the nearest-prior rate.
    fx_dates  = [r[0] for r in fx_rows]
    fx_values = [r[1] for r in fx_rows]

    import bisect
    out_rows = []
    for r_date, r_thb_per_kg in rubber_thb:
        if r_thb_per_kg is None:
            continue
        # Find rightmost FX date <= r_date
        idx = bisect.bisect_right(fx_dates, r_date) - 1
        if idx < 0:
            continue   # rubber observation predates our FX history
        fx_thb_per_usd = fx_values[idx]
        if not fx_thb_per_usd or fx_thb_per_usd <= 0:
            continue
        usc_per_kg = float(r_thb_per_kg) / float(fx_thb_per_usd) * 100.0
        out_rows.append((
            r_date, usc_per_kg,
            "RUBBER_TSR20",
            "Rubber STR 20 Bangkok (USc/kg, derived from THB price × THB/USD FX)",
            "derived:rubber_str20_usc",
            "USc/kg",
            "Daily",
        ))

    if out_rows:
        conn.executemany(
            "INSERT INTO time_series "
            "(date, value, series_id, series_name, source, unit, frequency, category) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, NULL)",
            out_rows,
        )
        conn.commit()
    return len(out_rows)


def compute_singapore_shipping_nowcast(conn: sqlite3.Connection) -> int:
    """Project the Singapore + Malacca subset of the shipping nowcast JSON
    into the time_series table.

    IMPORTANT data-shape note: PortWatch publishes 3 distinct stats per
    (port × day × vessel type):
      - calls           — single de-duped vessel arrival count (no direction)
      - imports_tonnage — cargo weight unloaded (inbound)
      - exports_tonnage — cargo weight loaded (outbound)
    The upstream JSON helpfully duplicates the `_calls` count under both
    `_imports_calls` and `_exports_calls` keys (they're literally identical).
    We follow the original shipping-nowcast dashboard's convention and use
    the EXPORTS key as the canonical un-duplicated source for calls.

    Tanker tonnage naming quirk: the upstream nowcast pipeline emits
    tanker tonnage under the *un-suffixed* key `singapore_<dir>_tonnage`
    (NOT `singapore_<dir>_tanker_tonnage`). See nowcast_pipeline.py:1826
    where `label_suffix = "_tonnage" if vt_key == "tanker"` short-circuits
    the otherwise-uniform `_<vt>_tonnage` pattern. Verified by cross-check
    against raw CSV: weekly-mean(daily-sum(import_tanker)) × 7 ≈ raw
    sum(import_tanker) for SG, so this key really is tanker-specific
    despite the misleading name. Documented in REGIONAL_TRADE_NOTES.md.

    Geographic coverage: country-level — aggregated across all 3 SG
    PortWatch ports (Singapore main, Serangoon Harbor, Singapore -
    Offshore Oil Terminal 1) via `groupby("date").agg(sum)` in
    `_run_aggregate_port_group` upstream.

    Reads `data/shipping/nowcast_results_s13.json` and writes:

      Overview:
        nowcast_sg_total_calls_actual / _cf  (all vessel types, exports key)

      Per vessel type (tanker, container) — 3 subchart streams each:
        nowcast_sg_<type>_calls_actual         / _cf  (de-duped count)
        nowcast_sg_<type>_imp_tonnage_actual   / _cf  (cargo unloaded)
        nowcast_sg_<type>_exp_tonnage_actual   / _cf  (cargo loaded)

      Malacca Strait overview:
        nowcast_malacca_total_actual / _cf

    Idempotent — wipes 'nowcast_*' rows before reinserting.
    """
    import json
    from pathlib import Path

    json_path = Path(__file__).resolve().parent.parent / NOWCAST_JSON_PATH
    if not json_path.exists():
        return 0

    with open(json_path) as f:
        payload = json.load(f)

    _wipe_series_prefix(conn, "nowcast_")
    out_rows = []

    # Singapore — same per-country generator used by the regional countries.
    # `iso2="sg"` keeps the existing series_id prefix (`nowcast_sg_*`).
    _emit_country_shipping_series(
        payload, out_rows,
        iso2="sg",
        country_display="Singapore",
        country_slug="singapore",
        country_label="SG",
    )

    # Regional countries — same shipping nowcast cards, served via the
    # country selector on the Regional Shipping tab. Loops over the 9
    # countries in REGIONAL_SHIPPING_COUNTRIES (Iran Monitor's regional
    # roster minus Taiwan, which the nowcast JSON doesn't carry).
    for iso2, c_display, c_slug, c_label in REGIONAL_SHIPPING_COUNTRIES:
        _emit_country_shipping_series(
            payload, out_rows,
            iso2=iso2,
            country_display=c_display,
            country_slug=c_slug,
            country_label=c_label,
        )

    # ── Malacca Strait overview ───────────────────────────────────────────
    mal = _stream_nowcast_series(payload, "Malacca Strait|total_count")
    if mal:
        dates, m_a, m_c = mal
        _emit_nowcast_pair(
            out_rows, dates, m_a, m_c,
            "nowcast_malacca_total_actual",
            "nowcast_malacca_total_cf",
            "Malacca Strait — total transits",
        )

    if not out_rows:
        return 0

    conn.executemany(
        "INSERT OR REPLACE INTO time_series "
        "(date, value, series_id, series_name, source, unit, frequency, category) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, NULL)",
        out_rows,
    )
    conn.commit()
    return len(out_rows)
