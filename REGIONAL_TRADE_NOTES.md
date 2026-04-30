# Regional Trade — Investigation Notes & Parked State

**Status as of 2026-04-30 (afternoon):**
- **Singapore Trade tab — DONE.** The SG-dependence-on-ME-fuels story is
  built and live (6 wide cards, one per SITC code, each with annual ME
  shares + monthly stacked levels). Sourced from the SingStat sheet via
  `trade_singstat`. See `page_layouts.py` → `singapore` → `trade` tab.
- **Regional Trade tab — CHEMICALS DONE.** 10 country cards live, each
  with annual SG-share (Comtrade, 2023+2024) on the left and monthly
  imports from SG (SingStat, with 2023-24 monthly avg benchmark) on the
  right. Comtrade dependence ingest ran 2026-04-30; ingested 9 of 10
  reporters cleanly (Vietnam 2024 still pending Comtrade publication —
  auto-fills on next runs via `only_stale=True`). See §7b for the bug
  we hit and fixed (W00 double-counting).
- **Regional Trade tab — MINERAL FUELS PARKED (waiting on data feed).**
  See §7c.

---

## 1. What we set out to build

Two complementary "exposure" stories on the dashboard's Trade tabs:

| Page | Story | Source(s) |
|---|---|---|
| Singapore Trade | SG's *dependence on the Middle East* for mineral fuels — what % of SG's mineral fuel imports come from each ME supplier | SingStat sheet (`SG_Annual_Imports`, `SG_Monthly_Imports` tabs) — already ingested into `trade_singstat` |
| Regional Trade | Each regional country's *dependence on Singapore* for chemicals + *dependence on the Middle East* for mineral fuels — what % of country X's chemical imports come from SG, and what % of country X's mineral-fuel imports come from ME | UN Comtrade — partial ingestion infrastructure built but not run |

The shared design pattern: **partner-share of imports**, computed as
`partner_value / world_value × 100` per (reporter, year, SITC code, partner).

---

## 2. Data we already have

### `trade_singstat` (populated, used by current dashboard cards)

3,832 rows across the three trade tabs of the colleagues' "dashboard data v2"
Google Sheet:

| Tab | Content | Rows |
|---|---|---|
| `SG_Annual_Imports` | SG mineral fuel imports by source country, annual 2023–25, with SITC sub-code breakdowns (3 / 333 / 334 / 335 / 343) | 935 |
| `SG_Monthly_Imports` | Same, but monthly (Apr 2025 onwards) | 2,081 |
| `SG_Chemicals_DX` | SG chemical exports (SITC 5) by destination country, hybrid annual 2023–25 + monthly 2026 | 816 |

Schema in `src/db.py` (lines around `CREATE TABLE trade_singstat`).
Columns: `period, frequency, flow, product_code, product_label,
partner_name, partner_iso2, partner_display, value_sgd_thou`.

The Regional Trade tab currently shows 10 per-country chemical-import
panels derived from `SG_Chemicals_DX` (we set this up before pivoting to
the dependence-ratio story).

The Singapore Trade tab now surfaces the `SG_Annual_Imports` and
`SG_Monthly_Imports` data via 6 wide cards (one per SITC code:
3 / 333 / 334 / 343 / 3346043 / 3431000), each with two side-by-side
subcharts: annual ME-supplier shares (UAE, Saudi, Qatar, Kuwait, Iraq,
Oman) on the left and monthly stacked levels on the right. Iran is
absent (sanctions; SG doesn't import from Iran). Tasks #41–43.

### `trade_comtrade_dep` (schema exists, table empty)

Created during this investigation, populated by zero ingest runs to date.
Schema:

```sql
CREATE TABLE trade_comtrade_dep (
    period          TEXT NOT NULL,    -- "YYYY-12-31" annual
    reporter_iso2   TEXT NOT NULL,
    partner_iso3    TEXT NOT NULL,    -- Comtrade ISO3, "W00" = World
    partner_name    TEXT NOT NULL,
    sitc_code       TEXT NOT NULL,    -- '5','51','54','3','333','334','343'
    value_usd       REAL NOT NULL,
    PRIMARY KEY (period, reporter_iso2, partner_iso3, sitc_code)
);
```

Plus indexes on reporter, partner, and sitc.

### Helpers in `src/db.py`

- `upsert_comtrade_dep_partition(conn, period, reporter_iso2, sitc_code, rows)`
  — wipes and rewrites one (period, reporter, sitc) partition. Idempotent.
- `comtrade_dep_partition_exists(conn, period, reporter_iso2, sitc_code)`
  — used by the ingestor's `only_stale` flag for resumable runs.

### Ingestor in `scripts/energy/update_data.py`

`fetch_comtrade_regional_dep(conn, only_stale=True)` — fetches
10 reporters × 7 SITC codes × 3 years = 210 calls with retry/backoff,
1.5s polite gaps, and resumable behaviour. The `[4b]` step in `main()`
that calls it is currently **commented out** — see `# [PARKED]` markers.

---

## 3. Investigation log — what we tried, what worked, what didn't

### Attempt 1: SingStat Table Builder for partner-level chemicals exports

**Hypothesis:** SingStat's M45xxxx tables would expose chemicals exports
broken down by partner country, monthly, going back to 2023.

**Probe:** `scripts/probe_singstat_chemicals.py`

**Finding:** The 9 working M45xxxx tables (M451001, 21, 31, 41, 51, 61,
71, 81, 91) all expose trade by *commodity* (SITC chapter / division /
group) but **none have a partner dimension**. SingStat organises trade
data either by commodity OR by country, never both at once.

**Implication:** SingStat alone can give us SG-aggregate chemical exports
by SITC chapter (M451041 specifically — Domestic Exports × 2-digit SITC,
1976→2026 monthly), but for the per-country breakdown we need a
different source.

This means the colleagues' `SG_Chemicals_DX` sheet must be aggregating
from a non-public-API source (probably TradeXplorer or an Enterprise
Singapore back-end). We can't replicate it ourselves from public APIs.

### Attempt 2: Comtrade SITC-Annual mode for regional dependence

**Hypothesis:** UN Comtrade has bilateral trade for the 10 regional
reporters (their imports broken down by partner), in SITC Rev 4 mode to
match the sheet's classification.

**Probe:** `scripts/probe_comtrade_regional_chem.py` (with multiple
revisions — see commits)

**Findings:**

1. **First run (SITC monthly, 2026 freshness check):** all reporters
   either returned `NO_DATA` or got rate-limited. Concluded that SITC
   monthly mode is patchy — many reporters only file monthly in HS, with
   SITC available only at annual frequency. Switched to SITC annual.

2. **Second run (SITC annual, sample years 2023/24/25):** values came
   back **mathematically impossible** (India 2024 SG share = 376%,
   Indonesia 2024 = 3,425,709%). Sensible values for some countries
   (China 2.82%, Japan 1.88%, Korea 2.49%).

3. **Diagnostic probe** (`scripts/probe_comtrade_world_aggregation.py`):
   Identified that `partnerCode=0` returns 173 rows for India 2024
   (instead of one "World" aggregate row) because Comtrade splits the
   response along the `partner2Code` dimension (secondary partner /
   re-routing classification). Our previous probe took `data[0]` which
   was an arbitrary row, not the World total. Sum across all 173 rows
   gave **$157.68B** = sensible India total chemical imports.

4. **Confirmed**: `isAggregate=True, aggrLevel=1, motCode=0,
   customsCode=C00` for all 173 rows — they're already chapter-level
   aggregates. Sum-all is the right strategy. SG share = $4.87B / $157.68B
   = **3.09%** for India 2024. Plausible.

### Attempt 3: All-partners-per-call ingest design

**Insight:** Querying with no `partnerCode` filter (plus
`partner2Code=0` to collapse the secondary-partner dimension) returns
one row per partner in a single call — much more quota-efficient than
per-partner queries.

- Quota math: 10 reporters × 7 SITC × 3 years = **210 calls** total
- Each call returns ~50–200 partner rows
- Final table size estimate: ~30k rows in `trade_comtrade_dep`

Schema designed to preserve raw partner detail so the renderer can
compute *any* share you want at chart time (ME aggregate / SG / China /
US / Other / etc.) without re-ingesting.

### Attempt 4: 2025 coverage check — the blocker

Earlier probe coverage at year-level showed:

| Reporter | 2023 | 2024 | 2025 |
|---|---|---|---|
| China | ✓ | ✓ | ∅ |
| India | ✓ | ✓ | ∅ |
| Indonesia | ✓ | ✓ | ✓ |
| Japan | ✓ | ✓ | ✓ |
| Malaysia | ✓ | ✓ | ✓ |
| Philippines | ✓ | ✓ | ∅ |
| South Korea | ✓ | ✓ | ∅ |
| Taiwan | ✓ | ✓ | ∅ |
| Thailand | ✓ | ✓ | ∅ |
| Vietnam | ✓ | ∅ | ∅ |

Only 3 of 10 countries had 2025 SITC-annual data published as of
2026-04-29. The 7 missing reporters publish on different lags; some
won't have 2025 in Comtrade until late 2026.

**This is what parked the work.** With only 3-of-10 coverage for 2025,
the dependence chart would render visually inconsistent (3 bars for
some countries, 2 for others), undermining the cross-country comparison
the dashboard is supposed to enable.

---

## 4. What we built but didn't run

### Schema (committed)

`trade_comtrade_dep` table + 3 indexes, created via `init_db()` in
`src/db.py`. Currently empty.

### Helpers (committed)

`upsert_comtrade_dep_partition` and `comtrade_dep_partition_exists`
in `src/db.py`.

### Ingestor (committed, runs cleanly, but disabled in pipeline)

`fetch_comtrade_regional_dep(conn, only_stale=True)` in
`scripts/energy/update_data.py`. Behaviour:

- Iterates 10 reporters × 7 SITC × 3 years
- Per-call: query Comtrade with no partner filter + `partner2Code=0`,
  sum returned rows by partner_iso3, write to DB
- `only_stale=True`: skips (reporter, sitc, year) partitions already
  present in the DB → restartable across days when rate-limited
- **Empty responses are NOT marked as ingested** — important, because
  many reporters publish 2025 data months late, so we want subsequent
  runs to retry the empties once Comtrade catches up
- Live progress printed per call (partner count, World total, SG share)
- **Coverage matrix** printed at end showing reporter × year completeness

### Documents (committed)

- `METHODOLOGY.md` — high-level project narrative
- `REGIONAL_TRADE_NOTES.md` — this file

### Probes (kept in `scripts/`)

- `probe_singstat_chemicals.py` — verified SingStat has no partner dim
- `probe_comtrade_regional_chem.py` — initial coverage probe (HS+SITC)
- `probe_comtrade_world_aggregation.py` — diagnosed the 173-row issue

### What's NOT done

- Ingest never run end-to-end (would take ~10 min for 210 calls)
- `derived_series.compute_regional_chem_dep_on_sg` not written (would
  compute the share ratios on top of `trade_comtrade_dep`)
- New chart_grid section type that consumes `trade_comtrade_dep`
  directly (or stacked-bar derived series) not built
- Regional Trade tab still shows the older per-country chemicals-export
  panels (sourced from SingStat sheet) — not the dependence-ratio
  story this work was building toward

---

## 5. Open questions / known issues

### 5.1 The 2025 coverage gap (the parking blocker)

What to do about it when resuming. Three documented options:

- **A. Drop 2025 entirely** — show 2-bar baselines (2023, 2024) for all
  10 countries. Visually consistent; loses one data point.
- **B. Probe Comtrade HS-Annual mode** — many reporters file faster in
  HS than SITC; ~30 min probe, may give us 2025 coverage for the
  missing 7 reporters. HS↔SITC mapping noise is small at chapter
  boundaries (we discussed: SITC 5 ≈ HS 28-39, SITC 51 ≈ HS 29,
  SITC 54 ≈ HS 30; ~2-3% drift).
- **C. CEIC for fresher reporter-level aggregates** — CEIC often has
  reporter trade aggregates faster than Comtrade. But CEIC's
  *bilateral* coverage (X reports trade with Y) is patchier than its
  aggregate coverage; may not give us the partner detail we need.

Recommendation: try **B** first (cheap probe), fall back to **A** if B
doesn't help. **C** is a future improvement, not a launch blocker.

### 5.2 SITC↔HS mapping if we go HS

| SITC | HS chapter(s) |
|---|---|
| 5 (chemicals total) | 28–39 |
| 51 (organic) → exclude | 29 |
| 54 (pharma) → exclude | 30 |
| 5 less 51 less 54 | 28 + 31–39 |
| 3 (mineral fuels) | 27 |
| 333 (crude petroleum) | 2709 |
| 334 (refined petroleum) | 2710 |
| 343 (natural gas) | 2711 |

### 5.3 ME partner set

Default suggested: IR, SA, AE, KW, IQ, QA, OM (7 countries — same as
the original ME dashboard's spotlight). Israel is technically ME but
not a fuel exporter; Bahrain is small; Yemen is offline. We can
expand this later by querying additional partners and re-aggregating
in the renderer (no re-ingest needed because we keep all partners).

### 5.4 Renderer pattern decision

When we resume, decide between:

- Pre-derive ratios as `time_series` rows (simpler, less flexible)
- New `trade_dep_grid` section type that queries `trade_comtrade_dep`
  directly (more flexible, more renderer code)

The doc earlier in this conversation included a sketch of the
section-config schema for the second approach.

---

## 6. Resume here

When picking this back up, the recommended order:

1. **Re-probe Comtrade HS-Annual** to test whether 2025 coverage
   improves vs SITC-Annual. Edit
   `scripts/probe_comtrade_regional_chem.py`: change `COMTRADE_URL` to
   `/data/v1/get/C/A/HS`, change `PROBE_SITC_CODE` to `'28'` (a
   chemical chapter), rerun. Compare hit/miss matrix to the SITC run.

2. **Decide A vs B based on the coverage** — if HS gives us all 10
   reporters for 2025, switch the production ingest's `cl` from `S4`
   to `HS` and adjust `COMTRADE_DEP_SITC_CODES` to HS chapters
   `[28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 27]`. If not,
   drop 2025 from `COMTRADE_DEP_YEARS`.

3. **Re-enable the `[4b]` step** in `update_data.py`. Search for the
   `# [PARKED]` marker and uncomment the call.

4. **Run a fresh ingest** — `python3.11 scripts/energy/update_data.py`.
   ~10 min for 210 calls. Inspect the coverage matrix at the end.

5. **Build the derivation** (`compute_regional_chem_dep_on_sg` and
   sibling for ME exposure) in `src/derived_series.py`. Output:
   per-country annual time_series rows for the dashboard.

6. **Wire two new sections** on the Regional Trade tab in
   `src/page_layouts.py`: chemical dependence on SG + mineral fuel
   exposure to ME. Replace or augment the existing per-country
   chemical-import panels.

7. **Rebuild and review** the dashboard.

---

## 7. Quota & runtime reference

- **Comtrade Plus free tier**: ~250 calls/day with API key
- **Full ingest runtime**: 210 calls × 1.5s polite gap + ~1-2s network ≈
  10-12 min when fresh; faster when most partitions are skipped via
  `only_stale`
- **DB size impact**: ~30k rows in `trade_comtrade_dep`, well under 1
  MB. No concerns.

---

## 7a. Upstream cleanup candidate — shipping nowcast JSON

While building the Singapore Shipping tab (2026-04-29) we discovered that
the `nowcast_results_s13.json` file exposes the per-port-call count under
both `country:<C>_imports_<vt>_calls` and `country:<C>_exports_<vt>_calls`
keys — and the values are bit-identical (verified
`max |export_actual - import_actual| = 0.0000` for tanker, container, and
dry_bulk). PortWatch's underlying data has only one calls statistic per
(port × day × vessel type); the upstream pipeline is duplicating it under
both labels for symmetry.

The existing shipping-nowcast dashboard handles this by canonicalising on
the exports key (see `_vps_pull/shipping-nowcast-pipeline/scripts/build_nowcast_dashboard.py`
line 2119). The Iran Monitor consumer-side fix does the same.

**Possible upstream cleanup**: have the nowcast pipeline emit calls under
ONE key (drop the `_imports_calls` duplicate). Trade-offs:
- Saves ~50% of the JSON's calls-related rows
- Risk: any other consumer using the `_imports_calls` key would break
- Need a coordinated rollout across consumers
- Out of scope for the Iran Monitor session — flagging here for whenever
  someone next touches the `shipping-nowcast-pipeline` codebase.

### 7a.1 Tanker tonnage naming quirk (related)

Initial assumption was that the JSON had no tanker tonnage data — wrong.
Tracing through `nowcast_pipeline.py:1821-1827`:

```python
for vt_key, vt_col in VESSEL_TYPES:
    tonnage_col = f"{import_or_export}_{vt_col}"   # "import_tanker"
    if tonnage_col in df.columns:
        agg_specs[f"{vt_key}_tonnage"] = (tonnage_col, "sum")
        label_suffix = "_tonnage" if vt_key == "tanker" else f"_{vt_key}_tonnage"
        metric_labels[f"{vt_key}_tonnage"] = f"{slug}{label_suffix}"
```

The `label_suffix` line short-circuits the suffix for tanker — so tanker
tonnage gets emitted under `country:singapore_<dir>_tonnage` (no
`_tanker_` infix) while all other vessel types use the suffixed
`country:singapore_<dir>_<vt>_tonnage` pattern. This is confusing because
the un-suffixed key reads like "total" when in fact it's tanker-only.

Verified by cross-check against raw CSV: sum of weekly actual values
≈ raw `sum(import_tanker)` ÷ 7 (weekly mean of daily port-summed values
× 7 days/week recovers the daily total). Numbers match within rounding,
confirming the un-suffixed key is genuinely tanker-specific.

The original shipping-nowcast dashboard already handles this in
`build_nowcast_dashboard.py:1992-1994` (special-cases tanker to use the
un-suffixed key). Iran Monitor's `derived_series.compute_singapore_shipping_nowcast`
matches that convention.

**Possible upstream cleanup**: rename the emitted key to
`country:<C>_<dir>_tanker_tonnage` for consistency with the other 4
vessel types. Same coordination caveats as 7a — any downstream
consumer expecting the un-suffixed key would break.

---

## 7b. Bug fixed — W00 double-counting in the dependence derivation

When `compute_regional_chem_share_from_sg` first ran (2026-04-30) it
produced shares that were ~half of what the Comtrade ingest log had
shown (e.g., Malaysia 2024 SITC 5: log said 11.74%, derivation said
5.67%).

**Cause:** `trade_comtrade_dep` stores BOTH the `W00` (Comtrade-supplied
"World" aggregate) row AND rows for every individual partner. The
individual partner values sum to the same total as W00, so summing
"all partner rows" double-counts the world.

**Fix:** the derivation now uses the `W00` row directly as the
denominator instead of summing `partner_industrial.values()`. See
`compute_regional_chem_share_from_sg` in `derived_series.py`.

**Watch for:** any future derivation that reads `trade_comtrade_dep`
and tries to compute totals must either (a) use the W00 row directly,
or (b) explicitly filter `partner_iso3 != 'W00'` when summing partners.
The redundancy is intentional — keeping both rows gives us flexibility
to compute partner-specific shares without re-fetching.

---

## 7c. Mineral fuels regional dependence — PARKED

Same dependence story as the chemicals card, but for mineral fuels
(SITC 3 + 333/334/343). Data scoping done 2026-04-30:

**Findings on the four candidate SITC codes:**
| SITC | What | SG share story |
|---|---|---|
| 3   | Mineral fuels TOTAL | 0.2-1% for most countries; **29% for Indonesia, 19% for Malaysia** (reflects refined-product reweighting) |
| 333 | Crude petroleum     | ≈0% across all 10 reporters — SG produces no crude. Skip. |
| 334 | Refined petroleum   | THE STORY. **Indonesia 53%, Malaysia 34%**, others 6-10%. SG is the regional refining hub. |
| 343 | Natural gas         | ≈0% across the board. SG isn't a gas exporter. Skip. |

So only SITC 3 (chapter total) and SITC 334 (refined petroleum) are
worth displaying. The crude/gas categories are noise.

**Why parked:** the chemicals card pairs annual shares (Comtrade) with
monthly absolute imports (SingStat `SG_Chemicals_DX`). For mineral
fuels we'd want the same pairing — annual SG shares for each country
+ monthly absolute imports from SG to each country. **The monthly
companion data doesn't exist yet** — there's no `SG_Fuel_DX`
equivalent in the SingStat sheet. A colleague is going to add SG's
exports of SITC 334 to the regional countries to a similar sheet.
Until that lands, the cards would be annual-only and visually
different from the chemicals layout.

**Recommended layout once monthly data lands** (one wide combined card
per the chemicals pattern, dropping SITC 333/343):
- Section: "Mineral fuel imports from Singapore — by regional country"
- 10 country cards
- LEFT subchart: annual SG share (SITC 3 chapter, or SITC 334 — pick one
  or include both as grouped bars)
- RIGHT subchart: monthly imports from SG (whatever the colleague's
  feed provides) with 2023-24 monthly avg benchmark

**To resume:**
1. Get the new sheet/feed from the colleague — confirm what SITC level
   it's at (334? 3? both?), what countries are covered, and what
   reporting frequency (monthly assumed).
2. Extend `fetch_singstat_trade_from_gsheets()` (in `update_data.py`)
   to ingest the new tab into `trade_singstat` with a new product_code.
3. Add a derivation `compute_regional_fuel_imports_from_sg(conn)`
   producing alias series `regional_fuel_imports_from_sg_<iso2>`
   parallel to the chemicals one.
4. Add the section in `page_layouts.py` mirroring the chemicals
   combined card.

The annual SG-share derivation
(`compute_regional_chem_share_from_sg`) can be generalised to handle
fuel SITC codes too — it's already partner-summing from
`trade_comtrade_dep`. Just parameterise the SITC list.

---

## 8. References

- Methodology doc: `METHODOLOGY.md` (sections 3 "Data sources", 5 "Key
  design decisions" cover trade-related infrastructure)
- DB schema: `src/db.py`
- Ingestor: `scripts/energy/update_data.py` →
  `fetch_comtrade_regional_dep`
- Investigation probes: `scripts/probe_singstat_chemicals.py`,
  `scripts/probe_comtrade_regional_chem.py`,
  `scripts/probe_comtrade_world_aggregation.py`
- Country mapping (SingStat names → ISO2): `src/country_mapping.py`
- Existing dashboard cards (chemical exports per country, from the
  SingStat sheet): see `regional` page in `src/page_layouts.py` →
  `trade` tab → "Chemical imports from Singapore" section
