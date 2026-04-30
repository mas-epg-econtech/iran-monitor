# Iran Monitor — Methodology & Build Record

A static, multi-page economic dashboard tracking how the Iran war and broader
Middle East stress are transmitting into Singapore's economy and the wider
Asian region. This document captures the build process, the design choices
made along the way, and the rationale behind them — intended both as
maintainer reference and as a portfolio narrative.

---

## 1. Project framing

### Goal

Produce a single dashboard that consolidates three previously-separate
analyses:

1. **Middle East Energy Dashboard** — global energy / refined product /
   industrial-input prices and Singapore-side macro pass-through
2. **Shipping Nowcast** — actual-vs-counterfactual vessel flows through
   regional chokepoints
3. **Asia regional indicators** — financial markets and country-level macro
   data for the 10 Asian economies most exposed to ME stress

The product needs to be:

- **Self-contained** — one folder, one DB, one builder script. No live
  cross-project dependencies.
- **Statically renderable** — output is HTML files committed to a public
  GitHub Pages site. No backend.
- **Refreshable on a schedule** — re-runs the ingestion + render in one
  command and updates the DB + HTML files in place.
- **Editorially controllable** — chart titles, descriptions, and groupings
  driven by config rather than buried in renderer code.

### Audience

Primarily MAS internal economists. The dashboard should answer "what's
changing because of the Iran war" at a glance, with each chart panel
self-explanatory enough to read without prior context.

---

## 2. Architecture

### Folder layout

```
Iran Monitor/
  data/
    iran_monitor.db          Unified SQLite — all time-series + trade
    shipping/                JSON snapshots from the shipping nowcast pipeline
  src/
    db.py                    Schema + connection + replace_* helpers
    series_config.py         Per-series metadata (CEIC ids, units, frequencies)
    dependency_config.py     Transmission-graph nodes (label, description,
                             series_ids, sheet_keywords)
    page_layouts.py          Maps DB slices to page sections + tabs + cards
    series_descriptions.py   Friendly names + chart-card descriptions
    derived_series.py        Computed-from-other-tables series (MAS Core MoM,
                             SingStat chemical-export per-country views)
    country_mapping.py       SingStat country-name → display + ISO2
    flag_svgs.py             Inline SVG flags
    illustrations.py         Hero/landing SVGs
  scripts/
    energy/
      update_data.py         Main ingestion pipeline (CEIC + Sheets + SingStat
                             + Comtrade + Motorist)
    build_iran_monitor.py    Renders all 4 HTML pages from the DB
    migrate_*.py             One-off DB migrations (one per major change)
    probe_*.py               Discovery / debug scripts (CEIC search, SingStat
                             table catalog, Comtrade availability)
    inspect_gsheets.py       Google Sheets inspection tool
  index.html, global_shocks.html, singapore.html, regional.html
  assets/, logs/
```

### Data flow

```
[ External sources ]                          [ DB ]                [ HTML ]
                                            iran_monitor.db
  CEIC API ────────┐                       ┌────────────────┐
  SingStat APIs ───┼── update_data.py ──>  │  time_series    │ ──┐
  Google Sheets ───┤                       │  trade          │   │ build_iran_monitor.py
  UN Comtrade ─────┤                       │  trade_singstat │   ├──> 4 self-contained HTML files
  Motorist scrape ─┘                       │  metadata       │ ──┘    (no JS framework, just
                                            └────────────────┘         Chart.js + Luxon CDN)
                                                  │
                                                  └── derived_series.py recomputes after ingest
```

The pipeline is deliberately one-way: external → DB → static HTML. There's
no live querying, no API server, no client-side data fetch. This makes the
output cheap to host (GitHub Pages) and impossible to break in production.

### One DB, source-isolated ingestion, unified queries

A central design decision was to store *all* time-series in a single
`iran_monitor.db` regardless of source, with a `source` column distinguishing
them at query time. The alternatives we considered:

- **Per-source DBs** (one for CEIC, one for Bloomberg, etc.): cleaner
  separation but every query needs `ATTACH DATABASE`, and the renderer would
  have to know which source each indicator lives in.
- **Per-page DBs** (one for Singapore, one for Regional, etc.): forces page
  boundaries into the data layer, so a series used on multiple pages would
  need duplication or cross-DB joins.

The single-DB-with-source-column design lets the renderer pull any slice by
`series_id` without caring where it came from, while ingestion stays
source-isolated (each fetcher writes only its own series, doesn't touch
others). Trade data lives in its own tables (`trade`, `trade_singstat`)
because its shape (partner × period × product) doesn't fit the time-series
table.

### Renderer model: config-driven, not template-driven

Instead of writing one template per page, every page is generated from a
declarative config in `src/page_layouts.py`. Each page is a list of
sections; each section can be a `chart_grid`, a `pdf_cards` block, a
`shipping_iframe`, or a `placeholder`. Sections reference data by either:

- A **dependency_config node ID** (a logical concept like `"sg_cpi"` or
  `"crude_oil"` that resolves to a list of series_ids at build time)
- A **per-card override dict** (`{"label": "China", "series": [...]}`) when
  we want to break out of the node abstraction

This separation lets editorial choices (chart title, description, ordering)
live in `page_layouts.py` while the data wiring lives in
`dependency_config.py`. New series go in `series_config.py`; deciding which
chart they appear on is a separate, page-specific decision.

---

## 3. Data sources & ingestion

### CEIC (`src/series_config.py`, ingestor: `fetch_ceic_series`)

77 macro/financial indicators identified by CEIC numeric series IDs.
Authentication via `CEIC_USERNAME` / `CEIC_PASSWORD` in `.env`. Used for:

- Singapore CPI, MAS Core inflation (level + derived MoM), DSPI / IPI / EPI
  / MPPI sub-aggregates
- Singapore sectoral activity (sea cargo, container throughput, flight
  movements, F&B sales, etc.)
- Singapore retail fuel prices (4 grades from SingStat distributed via CEIC)
- Singapore construction materials prices + demand (10 series)
- Singapore real-estate (URA Property Price Index + transaction count)
- Global energy benchmarks (crude WTI/Brent, US natural gas, German gas,
  naphtha)
- Regional headline + core CPI YoY for 10 Asian economies (20 series)
- Regional industrial production YoY for 10 economies (10 series — one
  per country, hand-picked from a CEIC freshness audit)

Where MAS doesn't publish a metric directly (e.g., MAS Core MoM), we pull
the level and derive the change in `src/derived_series.py`.

### Google Sheets — Bloomberg prices (`scripts/energy/update_data.py`)

Service-account auth (`GOOGLE_SERVICE_ACCOUNT_FILE` in `.env`) reads the
"dashboard data v2" workbook colleagues maintain. The sheet has 5 tabs:

- `Refined Product Prices` (16 Bloomberg series — VLSFO, jet fuel, gasoline,
  naphtha, LPG)
- `Industrial Input Prices` (9 Bloomberg series — ethylene, polyethylene)
- `SG_Annual_Imports`, `SG_Monthly_Imports`, `SG_Chemicals_DX` (SingStat
  trade data the colleagues pre-aggregated)

The price tabs use `name → unit → frequency` rows above the data; the
parser supports per-series frequency (the sheet's prior layout was one tab
per frequency — refactor documented in section 5).

Each Bloomberg series is stored under a stable name-based ID
(`gsheets_<slug>`) so future tab reorganisations don't break references.
The `dependency_config.py` `google_sheet_series` field uses the human
series name; the renderer resolves it via slugified prefix-match against
`series_id` LIKE `gsheets_<slug>%`.

### SingStat Table Builder (`fetch_singstat_merchandise`)

Public, no auth. Pulls structured monthly series for petroleum
imports/exports (`M451001`), construction contracts, wholesale trade
indices, electricity tariff, and IIP for specialty chemicals (`M355381`).
Each series is identified by a `<tableId>:<seriesNo>` source_key.

We migrated SG IIP from a frozen DataGov dataset (`M355301`, deprecated
Dec 2025) to the live `M355381` to pick up 2025-rebased data — documented
in `migrate_iip_to_m355381.py`.

### SingStat trade — via the colleagues' Google Sheet
(`fetch_singstat_trade_from_gsheets`)

The 3 trade tabs in the same sheet feed `trade_singstat`:

- `SG_Annual_Imports` + `SG_Monthly_Imports`: SG mineral fuel imports by
  source country (long format, country × year/month, with SITC codes 3, 333,
  334, 335, 341, 342, 343 broken out)
- `SG_Chemicals_DX`: SG domestic chemical exports by destination, hybrid
  layout (3 annual columns + 3+ monthly columns side-by-side)

Country names are mapped to display name + ISO2 via `src/country_mapping.py`
(~110 entries hand-curated from the partners that actually appear in the data).

### UN Comtrade (`fetch_trade_from_comtrade`)

API-key auth (`COMTRADE_API_KEY`). Currently pulls SG petroleum trade by
HS chapter (HS 27 family) monthly with partner-level breakdown. Retained
as a backup — the dashboard uses SingStat as the authoritative SG view —
and now being investigated as the source for regional dependence ratios
(country X's chemical imports from SG vs from World).

### Motorist.sg (`fetch_motorist_fuel_prices`)

Daily scrape of the Chartkick chart on motorist.sg's petrol prices page.
Multiple brands per day per grade, collapsed to a daily mean per
`(date, series_id)` in `replace_series` (the table's primary key is
`(date, series_id)` so we can't have multiple brand rows per day).

### Shipping nowcast (`data/shipping/`)

JSON files copied from a separate VPS pipeline that publishes
`nowcast_results_s13.json` and `crisis_deviation_summary.csv`. Iran Monitor
embeds the live shipping dashboard as an iframe rather than re-rendering
locally — keeps the existing dashboard (which has its own UI complexity)
authoritative.

---

## 4. Renderer

### Pages

Four self-contained HTML files, each with its own JS chart instances and
the same chrome (nav bar, date-range selector, data sources panel):

- `index.html` — landing with 3 nav cards (no charts)
- `global_shocks.html` — Energy + Shipping tabs (Bloomberg + CEIC)
- `singapore.html` — 5 tabs (Prices, Sectoral activity, Trade, Shipping,
  Financial markets)
- `regional.html` — 6 tabs (Prices, Sectoral activity, Trade, Shipping,
  Financial markets, MAS EPG reports)

Tabs are page-internal (JS-driven hide/show); each tab has its own
section list.

### Chart machinery (`build_chart_config`)

Single function builds a Chart.js v4 config from a list of series. Handles:

- **Line vs bar** charts (`chart_type="line"` or `"bar"`)
- **Time vs category x-axis** (`x_axis_type="time"` or `"category"`)
- **Single-unit Y-axis title** when all series in a chart share a unit
  (cleaner than repeating the unit on every legend label)
- **War-start vertical annotation** at 28 Feb 2026 on time-axis charts
- **Friendly legend labels** sourced from `series_descriptions.py`

### Layout machinery (`render_chart_grid`)

A chart_grid section emits a CSS-grid of `.chart-card` divs. Per section
options:

- `chart_type`, `x_axis_type` flow through to every card
- `columns: N` overrides the default `auto-fill, minmax(420px, 1fr)` to
  force exactly N columns per row (used for the trade tab where each row
  must show one country's annual + monthly side-by-side)
- `nodes` is an ordered list of either dependency-config node IDs or
  per-card override dicts — both formats produce one card each, in order

### Auto-split-by-unit

When a multi-series card has series in mixed units (e.g., LPG is sometimes
quoted in USD/gallon for US benchmarks, USD/metric tonne for Asia), the
renderer auto-splits into one card per unit. Editorial titles for these
split cards are configured in `series_descriptions.NODE_UNIT_TITLES`
(`{node_id: {unit: title_suffix}}`) — used to override the default
"Crude Oil — USD/Barrel" with something more descriptive.

### War-period zoom (unified across line & bar charts)

The default page-wide date range is "War period" (`Jan 2026 → today`).
The JS `applyDateRange("war")` and the Python first-paint setup share the
same logic:

- xMax = today (so the war-start annotation + any post-war gap stay visible)
- xMin = `WAR_ZOOM_START` (`2026-01-01`), unless the chart has fewer than
  `MIN_WAR_POINTS=8` distinct timestamps in the war window — in which case
  walk xMin backward through the actual data to surface ≥8 distinct
  timestamps (so low-frequency series like quarterly URA prices don't show
  as 1-2 dots floating in white space)

For category-axis charts (bar charts with discrete labels), the date range
selector is a no-op — the JS guard `if (xType !== "time") return` skips
them entirely.

### Source attribution

Each chart card displays a "meta block" listing every series's source chip
(CEIC / SingStat / Bloomberg / Motorist / etc.), name, frequency · unit,
and "Through {Mon YYYY}" date. When ≥4 series share source/freq/unit, the
block collapses into a single summary line. The page-bottom "Data sources"
panel aggregates every series across all charts on the page, filterable
by active tab.

---

## 5. Key design decisions, with rationale

### One DB, source-isolated ingest, unified queries
*See section 2.* Single source of truth for the renderer; isolated writers
for safe re-runs.

### `series_id` is stable; `series_name` is allowed to drift
Source data sometimes renames things (Bloomberg series get cleaner names,
CEIC series get rebased). Our `series_id` is either the source's stable
numeric id (CEIC) or a slugified hash of the human name (Bloomberg
`gsheets_<slug>`). The `series_name` field is just for display and
description and can change without breaking dependency_config wiring.

### Friendly names live in `series_descriptions.py`, not in `series_config`
Two reasons:
1. `series_config` is the registry of *what to fetch*; friendly names are
   the editorial layer. Mixing them creates a single bloated file.
2. Some series are wired up by name (Bloomberg via `google_sheet_series`)
   and some by ID (CEIC); `series_descriptions` does both lookups and the
   renderer doesn't have to care which.

### Replaced the per-tab Bloomberg layout with a stable name-based id
The colleagues' Google Sheet was reorganised from `Daily / Weekly / Monthly`
tabs (with frequency derived from tab name) to `Refined Product Prices /
Industrial Input Prices` content tabs (with per-series frequency in row 2).
We took the opportunity to make `series_id` tab-independent
(`gsheets_<slug>`), so future tab reorganisations don't churn the IDs in
the DB. The dependency-config resolver matches via slugified prefix on the
first 35 characters of the human name — robust to small label drift.

### Regional IPI: switched from level indices to YoY %
Originally we pulled each country's official IPI level. This had two
problems:
1. **Different base years** (China=2010, Korea=2020, Taiwan=2021, etc.) so
   levels weren't directly comparable across countries
2. **China's level series was discontinued in 2022-11**, leaving the chart
   empty for the war period

After a discovery probe across the 10 countries × {PMI, IPI YoY, IPI
Level} matrix (`audit_regional_activity_ceic.py`), we switched all 10 to
% YoY series:
- 8 countries: country-published IPI YoY
- South Korea: OECD harmonised manufacturing production (no clean KOSTAT
  monthly YoY surfaced)
- China: NBS Value Added of Industry YoY (the official PRC headline metric;
  the IPI level the colleagues' workbook listed was the deprecated 2010=100
  series)

This made the chart visually consistent (single % YoY axis across all 10)
and gave us through-2026-Q1 data for every country except Indonesia
(which has a fundamental BPS publication lag — no swap fixes it).

### Inflation chart titles → just "Annual" / "Monthly"
For both Singapore (`sg_cpi` node, 4 series across 2 units) and Regional
(10 country cards each with headline + core), the chart titles dropped
"Headline" because the cards show *both* headline and core. Section title
is "Inflation — Annual"; per-country card titles are just country names.
Legend labels are "Headline CPI" and "Core CPI" (Singapore: "MAS Core CPI").

### Trade tab on Singapore: bars in country pairs per row
The natural shape of the trade data is "for each country, here's the
annual baseline and the 2026 monthly detail." We render this as a 2-column
grid (`columns: 2`) where each row is one country: annual bar chart on
the left, monthly bar chart on the right. The 10 countries × 2 charts =
20 cards, paired by ordering them as `[annual_cn, monthly_cn,
annual_in, monthly_in, ...]`.

The CSS uses `repeat(2, 1fr)` (overriding the default auto-fill) so the
pairing holds at any desktop width. Mobile collapses to 1 column —
annual stacks above monthly per country, which still preserves grouping.

### War-period x-axis: data on the left, gap on the right
Stale-data charts (e.g., Indonesia IPI ending Dec 2025) used to fall back
to the "All time" view in war mode, looking visually inconsistent with
their fresh siblings. The unified rule (xMax = today, xMin = `2026-01-01`
walked back to ≥8 timestamps) keeps the x-axis width consistent across
sibling charts: stale series cluster their data on the left and show an
empty gap on the right where the war period would be — visually honest
about what's missing.

### Bar charts use category axis (no war line)
For sparse discrete observations (the trade-tab annual + monthly charts),
category-axis bars work better than time-axis bars (no awkward gaps for
unequal time spacing). Category axes naturally ignore the war-zoom
selector. The war-line annotation is also skipped — for a 3-bar annual
chart the war line would just fall off the right edge.

---

## 6. Status

### Built and live

- All 4 pages render with real data
- 77 CEIC series ingest cleanly
- 25 Bloomberg series ingest from the v2 sheet
- 3 SingStat trade tabs ingest into `trade_singstat`
- 7 SingStat Table Builder series for petroleum / construction / electricity
- 16,000+ Comtrade rows (currently unused by the renderer; backup data)
- Motorist daily prices for 5 grades
- Singapore page: Prices + Sectoral Activity tabs fully wired, Trade tab
  populated with SG mineral-fuel imports
- Regional page: Prices + Sectoral Activity tabs fully wired (CPI + IPI
  for 10 countries), Trade tab has chemical-imports-from-SG bars (10
  country rows × annual + monthly), Financial Markets fully wired, MAS
  EPG Reports tab linked to 6 internal PDFs
- Global Shocks page: Energy + Shipping tabs fully wired
- War-period zoom unified across all chart types
- Bar chart support with category-axis x and 2-column row layout
- Per-country derived series for SingStat chemical exports (10 annual + 10
  monthly = 20 series_ids derived from `trade_singstat`)

### Known to-dos

- **Regional Trade dependence ratio** (parked 2026-04-29 — see
  `REGIONAL_TRADE_NOTES.md` for the full investigation log). Schema +
  ingestor are built and tested; pipeline call is commented out in
  `update_data.py` step `[4b]`. Parking trigger was that Comtrade
  SITC-Annual 2025 coverage only included 3 of 10 reporters as of the
  parking date — would have produced visually inconsistent dependence
  charts. The notes doc has a resume checklist (probe HS mode for
  better 2025 coverage; or drop 2025 and ship with 2-bar baselines).
- **Singapore Trade dependence widget** (planned): port the original ME
  dashboard's "spotlight (ME) / custom" multi-line chart pattern for
  showing SG mineral-fuel imports by source. ME spotlight = Iran,
  Saudi, UAE, Kuwait, Iraq, Qatar, Oman; Custom mode reveals all ~80
  partners as a multi-select.
- **LLM narrative regeneration**: the scaffolding from the precursor
  Energy Dashboard imports `from build_dashboard import ...` which
  doesn't exist in Iran Monitor. Currently fails silently in step
  `[7/7]`. Either port the missing helpers or rip out the narrative
  step entirely.
- **`\/` deprecation warning** in the Motorist parser — Python 3.12 will
  promote it to an error. Fix by sanitising input before
  `decode("unicode_escape")`.
- **Refresh orchestrator** (`scripts/refresh_data.py`): a single command
  that runs `update_data.py` then `build_iran_monitor.py`. Currently
  invoked separately.
- **Per-source ingestion module split**: `scripts/energy/update_data.py`
  has grown to ~1000 lines covering 6 different sources. Refactor into
  `scripts/ingest/{ceic,gsheets,singstat,comtrade,motorist}.py` with a
  shared orchestrator. Cleanup task — not blocking.
- **Cleanup**: delete the legacy `data/dashboard.db` and
  `data/asean_markets.db` (now subsumed into `iran_monitor.db`); update
  the README to reflect the unified DB.

### Live deployment

Pushed to GitHub Pages at
`https://mas-epg-econtech.github.io/iran-monitor/`. Auto-deploys on push
to `main`. The shipping nowcast iframe points at the sister site
`https://mas-epg-econtech.github.io/shipping-nowcast/`.

---

## 7. Methodology highlights (for showcase)

### Decision log lives in commit messages and migration scripts
Every non-trivial change is either a commit with a meaningful message
explaining the *why* not just the *what*, or a one-off `migrate_*.py`
script with a docstring stating the problem it solves. Examples:

- `migrate_swap_regional_ipi_to_yoy.py` documents why we abandoned IPI
  level series for YoY % across the 10 regional countries
- `migrate_swap_gsheets_layout.py` cleans up the orphaned
  `gsheets_daily_*` rows from before the colleagues reorganised the
  workbook
- `migrate_add_mas_core_mom.py` notes that MAS doesn't publish Core
  Inflation MoM directly so we derive it from the level index

These migrations are also rerunnable (idempotent via INSERT OR REPLACE)
which makes them a safe debugging sandbox.

### Discovery probes before commitment
Before adding a new data source we write a probe script that just looks:

- `find_ceic_series.py` — searches CEIC by keyword
- `find_fresh_regional_ipi.py` — finds CEIC alternatives when a series
  goes stale
- `audit_regional_activity_ceic.py` — cross-country audit comparing
  PMI vs IPI Level vs IPI YoY freshness across 10 reporters
- `inspect_gsheets.py` — dumps the structure of an arbitrary Google Sheet
- `probe_singstat_chemicals.py` — walks the SingStat table catalog
- `probe_comtrade_*.py` — verifies Comtrade availability + diagnoses
  data shape before a full ingestion

This pattern keeps quota usage minimal, lets us reason about source
quality before wiring, and produces audit trails (saved probe outputs
become the rationale for design choices).

### Editorial layer separated from data layer
Friendly names, chart titles, descriptions, page layouts, and section
ordering are all in dedicated config files. Tweaking copy doesn't touch
the renderer or ingestion. Adding a new chart doesn't require code
changes — just config edits. This reflects the dashboard's actual
maintenance pattern: structure changes occasionally, but copy + chart
selection changes constantly.

### Defensive ingestion
Every fetcher handles its own failure modes (CEIC empty responses,
SingStat 404 on table_id, Comtrade rate limits with retry+backoff,
Bloomberg `#N/A` cells, Motorist multi-brand row collisions). A single
source failing degrades gracefully — the page still renders, just with
that chart missing or stale.

### Static-by-design output
The output is plain HTML with inline JS and inline data — no build
toolchain (no webpack, no React, no SSR). The only runtime dependencies
are Chart.js, Luxon, and the chartjs-plugin-annotation, all from CDN.
This makes the dashboard:

- Cheap to host (GitHub Pages free tier)
- Resilient to outages (no API server to maintain)
- Trivially shareable (a single `.html` file works offline if the CDN
  scripts are cached)
- Auditable (the rendered HTML is the executable spec; no build step
  hides anything)

---

## Appendix: Tooling references

- **CEIC Python SDK**: `ceic_api_client.pyceic` (MAS-licensed, requires
  network access to CEIC servers)
- **SingStat Table Builder**:
  `https://tablebuilder.singstat.gov.sg/api/...` (public, no auth)
- **UN Comtrade Plus API**: `https://comtradeapi.un.org/data/v1/get/...`
  (free tier, ~250 calls/day with API key)
- **Google Sheets API**: service account JSON key, read-only scope
- **Chart.js v4** + `chartjs-adapter-luxon` + `chartjs-plugin-annotation`
  (CDN'd from cdnjs.cloudflare.com)
- **GitHub Pages**: deploys on push to `main`

## Appendix: Conventions

- Every `migrate_*.py` script follows the `/tmp` scratch + `shutil.copy`
  pattern (the FUSE-mounted Cowork folder doesn't fully support SQLite
  writes, so we build in `/tmp` and copy back atomically).
- Every fetcher in `update_data.py` writes its own `metadata`
  freshness-key (`ceic_last_updated`, `google_sheets_last_updated`, etc.)
  so the dashboard can show "data through Apr 2026" attribution.
- All series_ids that are derived (not fetched directly) get
  `source = 'derived'` or `source = 'singstat'` (when projected from a
  trade table) so the source-chip renderer can mark them appropriately.
