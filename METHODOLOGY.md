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

~95 macro / financial indicators identified by CEIC numeric series IDs.
Authentication via `CEIC_USERNAME` / `CEIC_PASSWORD` in `.env`. Used for:

- Singapore CPI, MAS Core inflation (level + derived MoM), Domestic Supply
  Price Index, Import / Export / Manufactured Producer Price indices
- Singapore sectoral activity — sea cargo, container throughput, Changi
  flight / passenger / freight movements, visitor arrivals by land
- Singapore retail fuel prices (4 grades from SingStat distributed via CEIC)
- Singapore construction materials prices + demand (8 series after dropping
  ready-mixed concrete per dashboard feedback)
- Singapore real-estate — URA Property Price Index + monthly transactions
- Singapore IIP series — Petroleum, Petrochemicals, Specialty Chemicals,
  Other Chemicals (migrated from SingStat M355381 to direct CEIC IDs in
  the 2026-04-30 SG-Activity feedback pass)
- Singapore Foreign Wholesale Trade Index — Overall + Petroleum & Petroleum
  Products + Chemicals & Chemical Products + Ship Chandlers & Bunkering
  (4 monthly series at 2017=100; replaced two quarterly SingStat WTI series)
- Singapore F&B Services Index — Overall + 5 segments (restaurants, fast
  food, caterers, food courts, cafes; chained-volume, 2017=100)
- Global energy benchmarks (crude WTI/Brent, US natural gas, German gas,
  Japan/France naphtha)
- Regional headline + core CPI YoY for 10 Asian economies (20 series)
- Regional industrial production YoY for 10 economies (10 series — one
  per country, hand-picked from a CEIC freshness audit)
- Regional financial markets — ASEAN+VN sovereign 10Y bond yields, LME
  Nickel front-month, Bangkok STR 20 rubber (THB/kg, converted to USc/kg
  via daily FX in `derived_series.py`)

Where MAS doesn't publish a metric directly (e.g., MAS Core MoM), we pull
the level and derive the change in `src/derived_series.py`.

### Google Sheets — Bloomberg prices (`scripts/energy/update_data.py`)

Service-account auth (`GOOGLE_SERVICE_ACCOUNT_FILE` in `.env`) reads the
"dashboard data v2" workbook colleagues maintain. The sheet has 7 tabs:

- `Refined Product Prices` (~16 Bloomberg series — VLSFO, jet fuel,
  gasoline, naphtha, LPG)
- `Industrial Input Prices` (~9 Bloomberg series — ethylene, polyethylene)
- `SG Financial Markets` (~11 Bloomberg series — USD/SGD spot + forwards,
  NEER/REER, USD/SGD implied vol, BVAL SGS yields, interbank o/n, STI,
  FTSE ST Real Estate)
- `SG_Annual_Imports`, `SG_Monthly_Imports`, `SG_Chemicals_DX`,
  `SG_Petroleum_DX` (SingStat trade pre-aggregated by colleagues)

The price tabs use `name → unit → frequency` rows above the data; the
parser supports per-series frequency (the sheet's prior layout was one tab
per frequency — refactor documented in section 5).

Each Bloomberg series is stored under a stable name-based ID
(`gsheets_<slug>`) so future tab reorganisations don't break references.
The `dependency_config.py` `google_sheet_series` field uses the human
series name; the renderer resolves it via slugified prefix-match against
`series_id` LIKE `gsheets_<slug>%`.

### Financial markets fetchers (`scripts/energy/financial_markets_fetchers.py`)

Three lightweight fetchers feeding the Regional Financial Markets tab:

- **yfinance** — 13 tickers covering 7 Asian FX vs USD (IDR/MYR/PHP/THB/VND/
  JPY/CNY), US 10Y Treasury yield, Brent ICE futures, COMEX gold/copper,
  LME aluminum 3M, JKM LNG ICE futures. Backfills ~365 days per call;
  uses `replace_series`. No auth required.
- **ADB AsianBondsOnline** — 5 ASEAN+VN sovereign 10Y yields. Currently
  disabled (ADB scrape gives only one daily point at a time and is brittle);
  superseded by CEIC sources for these 5.
- **investing.com** (with optional residential proxy via `PROXY_URL`) —
  CPO front-month on Bursa Malaysia and Newcastle FOB thermal coal.
  Single value per call; upserts.

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

The 4 trade tabs in the same sheet feed `trade_singstat`:

- `SG_Annual_Imports` + `SG_Monthly_Imports`: SG mineral fuel imports by
  source country (long format, country × year/month, with SITC codes 3, 333,
  334, 335, 341, 342, 343 broken out)
- `SG_Chemicals_DX`: SG domestic chemical exports by destination, hybrid
  layout (3 annual columns + 3+ monthly columns side-by-side)
- `SG_Petroleum_DX`: same hybrid layout for SITC 334 refined petroleum
  exports (added to support the Regional Trade Exposure refined-petroleum
  view, which is the higher-magnitude regional dependence story than the
  industrial-chemicals view)

Country names are mapped to display name + ISO2 via `src/country_mapping.py`
(~110 entries hand-curated from the partners that actually appear in the data).

The chemicals and petroleum DX tabs share a generic parser
(`_compute_singstat_export_country_series` in `derived_series.py`,
parameterised on `product_code`) so adding more product views requires
only a new tab + `partial(...)` call.

### UN Comtrade (`fetch_trade_from_comtrade` + `fetch_comtrade_regional_dep`)

API-key auth (`COMTRADE_API_KEY`). Two distinct ingestors:

- **SG petroleum trade by HS chapter** (HS 27 family) — monthly with
  partner-level breakdown. Retained as backup; not used by the renderer
  in the current build (SingStat is the authoritative SG view).
- **Regional dependence ratios** (`trade_comtrade_dep` table) — annual
  SITC 5 / 51 / 54 / 3 / 333 / 334 / 343 import values for 10 reporters
  (CN/IN/ID/JP/MY/PH/KR/TW/TH/VN), partner = SG vs partner = World (W00).
  Used to derive `regional_chem_share_from_sg_<iso2>` and
  `regional_fuel_share_from_sg_<iso2>` — the % of each reporter's
  imports of that product that comes from Singapore. The renderer's
  Regional Trade Exposure tab consumes these via the `view_selector`
  + `country_share_comparison` pattern. Coverage is 2023+2024 (we
  dropped 2025 because of incomplete reporter coverage at parking time).
  Empty (reporter, year, SITC) combinations are retried automatically
  on subsequent runs.

### Motorist.sg (`fetch_motorist_fuel_prices`)

Daily scrape of the Chartkick chart on motorist.sg's petrol prices page.
Multiple brands per day per grade, collapsed to a daily mean per
`(date, series_id)` in `replace_series` (the table's primary key is
`(date, series_id)` so we can't have multiple brand rows per day).

### Shipping nowcast (`scripts/shipping/`)

The shipping nowcast pipeline runs locally as part of `update_data.py`
(steps 7 + 8) — Iran Monitor is fully self-contained for shipping data,
no VPS dependency.

- **`download_portwatch_data.py`** (step 7) — incremental pull from IMF
  PortWatch's public ArcGIS API for daily ports + chokepoints data.
  No API key required. Cheap on most days (PortWatch publishes weekly
  on Tuesday EST, so most runs return zero new rows).
- **`nowcast_pipeline.py`** (step 8) — STL decomposition + Ridge
  regression on the PortWatch series. Produces
  `data/shipping/nowcast_results_s13.json` (~150 MB) and
  `crisis_deviation_summary.csv`. Compute: ~30-90s when it runs.

**Gating.** Step 8 is skipped when step 7's incremental download
brought no new data — measured by comparing the PortWatch CSV's max
date before vs after the download. Override with `--force-shipping`
(useful after a methodology change in `nowcast_pipeline.py`).

The Global Shocks page embeds the live VPS-hosted shipping dashboard
as an iframe (visual UI complexity is left to the upstream dashboard);
the Singapore Shipping tab renders the same nowcast data natively from
`time_series` (projected by `compute_singapore_shipping_nowcast` in
the second half of step 8).

The Ridge regression's control variables (FRED + EIA) are static —
frozen at last pre-crisis value as part of the methodology, cached at
`data/controls/{fred,eia}/` and don't need refreshing.

---

## 4. Renderer

### Pages

Four self-contained HTML files, each with its own JS chart instances and
the same chrome (nav bar, date-range selector, data sources panel):

- `index.html` — landing with 3 nav cards + 2 LLM-generated status
  indicators (planned, see Section 7)
- `global_shocks.html` — Energy + Shipping tabs (Bloomberg + CEIC)
- `singapore.html` — 5 tabs (Prices, Sectoral activity, Trade exposure,
  Shipping, Financial markets)
- `regional.html` — 6 tabs (Prices, Sectoral activity, Trade exposure,
  Shipping, Financial markets, MAS EPG reports)

Tabs are page-internal (JS-driven hide/show); each tab has its own
section list. Total chart count across the build is currently ~187
(57 SG + 15 Global + 115 Regional).

### Chart machinery (`build_chart_config`)

Single function builds a Chart.js v4 config from a list of series. Handles:

- **Line vs bar** charts (`chart_type="line"` or `"bar"`)
- **Time vs category x-axis** (`x_axis_type="time"` or `"category"`)
- **Single-unit Y-axis title** when all series in a chart share a unit
  (cleaner than repeating the unit on every legend label)
- **War-start vertical annotation** at 28 Feb 2026 on time-axis charts
- **Friendly legend labels** sourced from `series_descriptions.py`
- **Auto-quarterly x-axis ticks** — when all series in a chart are
  `frequency=Quarterly`, the x-axis switches from monthly ticks to
  `Q1 2025`-style quarter labels (Chart.js `time.unit: "quarter"` with
  `displayFormats: {quarter: "QQQ yyyy"}`). Applied to URA PPI; other
  cards remain monthly.
- **Forward-fill** for sparse multi-series charts where one series is
  much sparser than the others (e.g. PH 10Y bond auctions vs daily
  ASEAN-4 yields) — without this, Chart.js's `index`-mode tooltip
  silently drops the sparse series at hovered x-coordinates.

### Layout machinery (`render_chart_grid` and friends)

The renderer dispatches on `section.type`. Major section types:

- `chart_grid` — the workhorse. Emits a CSS-grid of `.chart-card` divs.
  Each item in `nodes` is either a dependency-config node ID (string) or
  a per-card override dict.
- `country_panels` — used by the Regional Shipping tab. Country selector
  drives N parameterised copies of a `subsection_template` (one per ISO2),
  each substituted via `{iso2}` / `{country}` placeholders. Lets us reuse
  the Singapore Shipping card layout per regional country without
  duplicating 11× in the layout config.
- `view_selector` — used by Regional Trade Exposure. A dropdown switches
  between named "views" each containing its own subsection list. The
  default view (currently Refined petroleum) is rendered first; others
  are hidden behind their key. Lets us put the chemicals and petroleum
  product views in the same tab without overwhelming.
- `country_share_comparison` — single grouped-bar chart that compares one
  share metric across N countries × M time periods. Used as the headline
  card on each Regional Trade Exposure view.
- `chart_grid` cards may also nest `subcharts` — a wide card containing
  multiple side-by-side sub-plots, sharing one card title + description
  + optional `single_legend` (a consolidated card-level HTML legend
  spanning all subcharts). Used by Singapore Trade Exposure (one card
  per SITC, paired annual-share + monthly-levels subcharts).

Per-section knobs:

- `chart_type`, `x_axis_type`, `stacked` flow through to every card
- `columns: N` overrides the default `auto-fill, minmax(420px, 1fr)` to
  force exactly N columns per row (used for trade-tab rows where each
  row pairs one country's annual + monthly side-by-side)
- `zoom_button: True` adds a per-chart "Zoom In/Out" toggle (Singapore
  Shipping nowcast cards open zoomed-in by default, mirroring the
  original ME shipping dashboard UX)
- `data_min_date: "YYYY-MM-DD"` clips out data points before that date
  on the rendered chart. Used on the SG Sectoral Activity tab for
  seasonal transport / F&B series (Jan 2025 minimum) per dashboard
  feedback.
- `hide_chart_title` / `hide_legend` — explicit overrides; default is
  auto (see "Redundancy auto-suppression" below).

### Redundancy auto-suppression

Card chrome triple-redundancy was a recurring complaint
(card `<h3>` ↔ Chart.js plugin title ↔ legend, all showing the same
text on single-series cards). Renderer now auto-suppresses:

- **Chart-level title** (Chart.js `plugins.title.display`) is hidden
  whenever the card has an `<h3>` above the canvas (always true for
  named cards). Only fired when `hide_chart_title is None` (the default);
  explicit values still win.
- **Legend** (`plugins.legend.display`) is hidden when the chart has
  exactly one series (the legend would just repeat the chart title).
- **Friendly-name title suffix** is appended only when a node produces
  multiple cards (e.g., jet_fuel emits 3 cards for NWE / SG / PADD-1, so
  the "— NWE FOB Barges" suffix is meaningful). For a single-card node
  the suffix is dropped — "Petroleum refining" not "Petroleum refining
  — IIP".

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

### Editorial pass conventions (2026-04-30 audit)
After a comprehensive audit of every card title and description across
all 3 pages, we adopted these rules:

- **Card titles** describe the content, not the unit or measurement label.
  "Petroleum refining" not "Petroleum refining — IIP"; "Private property
  price index" not "Real Estate — Private property PPI". Unit / variable
  references move into the description, where they have room to be
  contextualised.
- **Card descriptions** match exactly what the card shows. Two-card splits
  (water transport into sea-cargo + container-throughput, air transport
  into flights + passengers + freight) get per-card descriptions; the
  parent-node generic description doesn't carry over.
- **Descriptions ≤ ~210 characters (~3 lines).** Anything longer compresses
  the chart canvas; preserves visual rhythm.
- **No internal notes in descriptions** ("replaces the older …",
  "ready-mix concrete dropped per dashboard feedback") — those belong in
  commit messages and migration scripts.
- **No source-table-id references** in descriptions ("Source: SingStat
  M400001", "via SG_Chemicals_DX"). Source attribution lives in the
  expandable Data Sources panel at the bottom of each tab; descriptions
  speak to the reader, not the maintainer.
- **SITC codes belong in descriptions, not titles.** Trade Exposure card
  titles say "Crude petroleum oils" / "Refined petroleum products"; the
  description opens with the SITC code for cross-referencing.
- **Iran-relevance is part of the contract.** Each description should
  answer "what is shown" and "why it matters for the Iran-crisis
  monitoring story" — terse, no boilerplate.

### Stable, deterministic chart IDs
Earlier builds used counter-based IDs (`chart_petroleum_refining_10`)
which churned when cards were added or reordered. The renderer now emits
deterministic IDs of the form `<page>.<tab>.<card_slug>` (e.g.
`sg.activity.petroleum_refining`, `gs.energy.crude_oil`,
`regional.trade.refined_petroleum`). This:

1. **Makes anchor links durable** — bookmarkable, shareable in chat /
   email without breaking on rebuild.
2. **Lets the LLM narrative system cite charts unambiguously** —
   citations like "see chart `sg.activity.petroleum_refining` on
   Singapore › Sectoral activity" are stable across runs.
3. **Surfaces the ID to the viewer** — a small monospace badge in each
   card header (`⌗ sg.activity.petroleum_refining`) so a reader can
   match what the narrative refers to.

---

## 6. Status

### Built and live

- All 4 pages render with real data; ~187 charts total across the build
- ~95 CEIC series ingest cleanly
- ~37 Bloomberg series ingest from the v2 sheet (incl. SG Financial Markets)
- 4 SingStat trade tabs ingest into `trade_singstat` (annual imports,
  monthly imports, chemicals DX, petroleum DX)
- 2 SingStat Table Builder series for construction contracts + electricity
  tariff (petroleum/refining IIP migrated to direct CEIC)
- yfinance + investing.com financial-markets fetchers for FX, US 10Y,
  COMEX/LME commodities, JKM LNG, CPO, Newcastle thermal coal
- Comtrade regional dependence ingest — 2023 + 2024 SITC 5/51/54/3/333/
  334/343 across 10 reporters, fed into the Regional Trade Exposure tab
- Motorist daily prices for 5 grades
- **Singapore page** fully wired:
  - **Prices**: retail fuels (monthly + daily), electricity tariff, CPI
    headline + core (year-on-year + month-on-month), domestic supply /
    import / export / producer prices, construction material prices
  - **Sectoral activity**: petroleum refining IIP, petrochemicals IIP,
    specialty + other chemicals IIP, Foreign Wholesale Trade Index
    (4 monthly subsectors), water/air/land transport (Jan 2025 min),
    construction contracts + material demand, real estate (price index +
    deals), F&B Services Index (overall + 5 segments)
  - **Trade exposure**: 6 SITC cards (mineral fuels chapter total + crude
    + refined + gas + naphtha + LNG breakouts) each pairing annual ME
    shares + monthly stacked import levels; industrial-chemical exports
    card with regional partner shares + monthly levels
  - **Shipping**: PortWatch nowcast — Malacca Strait transits, total port
    calls, tanker + container vessel-type drill-down with per-vessel-type
    sub-charts (calls + import / export tonnage)
  - **Financial markets**: USD/SGD spot + forwards, NEER/REER, implied
    vol, FX turnover, SGS yield curve, BVAL yields, SORA 3M, interbank
    o/n, STI, SGX turnover
- **Regional page** fully wired:
  - **Prices**: per-country headline + core CPI YoY (10 economies)
  - **Sectoral activity**: per-country IPI YoY (10 economies)
  - **Trade exposure**: view selector for refined petroleum (default) and
    industrial chemicals — annual SG-share comparison + per-country
    monthly bar grids with 2023-24 benchmark
  - **Shipping**: per-country PortWatch panels via country selector
  - **Financial markets**: indexed FX vs USD, sovereign 10Y bond yields,
    commodities (Gold, Copper, Aluminum, Nickel, JKM LNG, Rubber TSR20,
    Newcastle Coal, CPO)
  - **MAS EPG Reports**: 6 internal PDFs linked
- **Global Shocks page**: Energy tab (crude / gas / refined products /
  industrial inputs) + Shipping tab (iframe to live nowcast dashboard)
- **War-period zoom** unified across all chart types
- **Bar chart support** with category-axis x and N-column row layout
- **Per-country derived series**: chemicals (10 annual + 10 monthly) +
  petroleum (10 annual + 10 monthly) + share derivations from Comtrade
- **Editorial pass complete**: titles, descriptions, redundancy
  suppression, ≤210-char descriptions, deterministic chart IDs (planned)
- **Pushed to GitHub** at `mas-epg-econtech/iran-monitor`
- **AI narrative system live** — landing-page status badges + narratives,
  per-page summary cards with chart citations, AI-disclosure footer.
  Sonnet 4.6 generates all four narrative payloads. σ-based trigger
  gating skips narrative regeneration when no curated indicator has
  moved beyond its 2σ threshold (computed from 2025 data) AND the last
  narrative is < 7 days old. See Section 7.

### Known to-dos

- **`\/` deprecation warning** in the Motorist parser — Python 3.12 will
  promote it to an error. Fix by sanitising input before
  `decode("unicode_escape")`.
- **Per-page selective narrative regeneration**: today, if any trigger
  fires, all 4 LLM calls run. Could optimise by only re-running the
  page(s) whose triggers fired plus the synthesizer (the two unchanged
  pages would be loaded from DB). Saves 30–70% of cost on partial-trigger
  runs but adds cache-coherence nuance. Defer until cost data warrants.
- **Per-source ingestion module split**: `scripts/energy/update_data.py`
  has grown to ~1700 lines covering 6 different sources. Refactor into
  `scripts/ingest/{ceic,gsheets,singstat,comtrade,motorist}.py` with a
  shared orchestrator. Cleanup task — not blocking.
- **Cleanup**: delete the legacy `data/dashboard.db` and
  `data/asean_markets.db` (now subsumed into `iran_monitor.db`); update
  the README to reflect the unified DB.
- **Singapore Trade interactive widget** — parked from the trade
  exposure refactor. Spotlight widget for trade-flow exploration.

### Live deployment

Pushed to GitHub Pages at
`https://mas-epg-econtech.github.io/iran-monitor/`. Auto-deploys on push
to `main`. The shipping nowcast iframe points at the sister site
`https://mas-epg-econtech.github.io/shipping-nowcast/`.

---

## 7. AI narrative system

The dashboard is augmented with AI-generated narratives that distil the
indicators into two headline judgements rendered on the landing page:

1. **How concerned should we be about the energy supply situation?**
2. **Are financial markets showing signs of tightening?**

All narratives, status calls, and key-driver bullets are generated by
**Claude Sonnet 4.6** at temperature 0.

### Status indicators (landing page)

Two prominent status badges on the landing page, one per question.
Each takes a 4-level scale:

| Level | Label | Color |
|-------|-------|-------|
| 1 | Calm | green `#10b981` |
| 2 | Watchful | amber `#f59e0b` |
| 3 | Strained | orange `#f97316` |
| 4 | Critical | red `#ef4444` |

Symmetric labels across both questions — keeps the visual reading clean.
Below each badge: a 3–4 sentence narrative summarising what's happening,
plus a collapsible "Key Drivers" section listing 3–5 short driver
bullets, each carrying inline anchor badges that link to the specific
charts on the relevant page that back up the call.

### Calibration philosophy

The 4-level scale is a **triage signal for an MAS audience, not a
description of absolute severity**. Critical is reserved for true
tail-risk realisations (Strait of Hormuz closure, multi-week tanker
stoppage, regional financial crisis) — the dashboard saying "something
is materially worse than yesterday — act now". Strained is the right
read for sustained war-period elevation, even when severe. If the badge
sat at Critical for the duration of a war it would stop carrying signal.

The synthesizer prompt encodes plain-English level descriptions plus
worked calibration examples per level per question (e.g., "Brent +50–100%
above baseline, refining IIP −15 to −30%, multiple shipping nowcast
pairs with 10–30% gaps, CPI passthrough in 1-2 regional countries → this
is squarely Strained"). The prompt also instructs the synthesizer to
bias toward the lower level when ambiguous.

### Why no deterministic threshold rules

An earlier iteration of the synthesizer used hard-coded numeric threshold
rules (e.g., `Critical iff max_score >= 90 AND multiple catastrophic
markers`). We deliberately moved away from this. The thresholds were
arbitrary (no defensible reason 89 is Strained but 90 is Critical), the
mechanical comparison wrapped what was already a judgement-laden score
(the LLM-emitted concern_score is itself a soft estimate), and in
practice the synthesizer LLM would override the rules anyway when its
qualitative read of the findings disagreed.

The judgement-based approach with worked examples is more honest: the
level is an AI judgement, anchored by specific calibration examples
written into the prompt. Tuning the calibration means editing example
descriptions, not nudging magic numbers. The previous threshold-rules
version of `prompts/synthesizer.md` is preserved at
`prompts/synthesizer.threshold-rules.md.bak` for reference.

### Architecture: 3 page-level + 1 synthesizer

Four LLM calls per refresh, all on **Claude Sonnet 4.6**:

1. **Global Shocks page** — analyses crude / gas / refined products /
   industrial inputs / Hormuz transit data. Writes to the energy-supply
   question only (financial markets isn't covered on this page).
2. **Singapore page** — analyses prices / sectoral activity / trade
   exposure / shipping / financial markets. Writes to both questions.
3. **Regional page** — analyses regional CPI / IPI / trade exposure /
   shipping / financial markets. Writes to both questions.
4. **Synthesizer** — reads the 3 page outputs (structured JSON), picks
   the two status badges, writes the landing-page narratives and
   per-driver chart citations.

Page-level granularity (rather than tab-level) because (a) tab boundaries
are presentation choices, not analytical ones, and (b) keeps cost and
orchestration manageable. Each page-level call still produces per-chart
structured findings so the synthesizer can cite specific charts.

### Pre-war baseline

Each indicator is compared against a **pre-war baseline** defined as the
monthly average of **November + December 2025** (the two months
immediately before `CRISIS_DATE`). For daily series, average daily
values across those two months; for quarterly series, use the Q4 2025
value. Computed by `scripts/compute_summary_stats.py`.

### Per-series stats fed to the LLM

The summary-stats extractor produces a uniform per-series payload, kept
intentionally generic so the LLM (not the extractor) owns the
analytical interpretation:

- `current` — value + date.
- `baseline` — Nov-Dec 2025 average + period + n_points (or null if no
  observations in window).
- `delta_vs_baseline` — `{abs, pct, kind}` where `kind` is `"pp"` for
  percentage-unit series (CPI YoY, yields, share %) and `"pct"` for
  level series (prices, indices). The `pct` field is null for `kind="pp"`
  so the LLM doesn't cite "percent of a percent".
- `trend_4w`, `trend_12w` — `{value, unit}` momentum signals; unit
  follows the same `pp`/`pct` convention.
- `war_period_range` — min, max, dates, n_points, plus a
  `current_pct_through_range` and convenience `at_war_high` /
  `at_war_low` flags (true when within 10% of an end AND ≥ 5
  war-period points).
- `stale` (boolean) + `data_age_days` — frequency-aware staleness
  (7d daily / 14d weekly / 45d monthly / 100d quarterly).

For shipping nowcast charts (PortWatch), the extractor also emits a
`nowcast_pairs` block with **actual-vs-counterfactual gap** stats per
pair: `gap_pct` (latest week), `gap_4w_avg_pct` (smoothed),
`war_max_gap_pct` + `war_max_gap_week`. The right framing for shipping
is actual-vs-cf, not actual-vs-baseline (which conflates seasonality);
the LLM is instructed to use these in the page prompts.

A top-level `_meta.charts_by_relevance` index pre-groups chart IDs by
relevance tag and page, so each page-level prompt can quickly enumerate
its in-scope charts without scanning the whole tree.

### Chart relevance tagging

Each chart is tagged with one or more of `["energy_supply",
"financial_markets"]`. This is set with a 3-level cascade (lower wins):

1. **Tab default** — `TAB_RELEVANCE` in `build_iran_monitor.py` maps each
   `<page>.<tab>` to its default tag list.
2. **Section override** — a section dict in `page_layouts.py` can set
   `relevant_to=[...]` to flip all its cards.
3. **Per-card override** — an individual node dict can set
   `relevant_to=[...]` to flip one card.

Live overrides are kept minimal: the only cascade in production is the
regional financial-markets tab, where the Commodity-prices section
flips from `financial_markets` (tab default) to `energy_supply` (since
JKM LNG / coal / copper / etc. are supply-cost signals), and the Gold
card flips back to `financial_markets` (safe-haven flow signal).

### Data flow

```
update_data.py  ──→  iran_monitor.db
                          │
                          ▼
        compute_summary_stats.py (walks page_layouts.py)
                          │
                          ▼
              data/summary_stats.json
                          │
              ┌───────────┼───────────┐
              ▼           ▼           ▼
        global_shocks.json  singapore.json  regional.json
              │           │           │
              └───────────┼───────────┘
                          ▼
                    synthesizer
                          │
                          ▼
        narrative_global_shocks   ┐
        narrative_singapore       ├─→  metadata table
        narrative_regional        │
        narrative_synthesizer     ┘
                          │
                          ▼
             build_iran_monitor.py reads narratives,
             renders status pills + expandable refs
             on landing page + per-page summary cards
```

### Prompt structure

Each prompt follows the slide-3-5 frame (Role & Objectives / Inputs &
Scope / Instructions / Guardrails) from `reference/dashboard_inputs.pptx`.
Page-level prompts differ only in scope and indicator list; role and
guardrails are templated.

**Per-page output schema** (JSON):
```json
{
  "page": "<page_slug>",
  "as_of_date": "YYYY-MM-DD",
  "energy_supply": {
    "concern_score": 0-100,
    "summary": "<2-3 sentence cross-cutting synthesis — NOT a recap of findings>",
    "key_findings": [
      {"finding": "...",
       "tab": "<tab_slug>",
       "chart_ids": ["sg.activity.petroleum_refining", ...]}
    ],
    "data_gaps": ["..."]
  },
  "financial_markets": { ... same shape, or null if N/A on this page }
}
```

**Synthesizer output**:
```json
{
  "as_of_date": "YYYY-MM-DD",
  "energy_supply": {
    "level": "calm | watchful | strained | critical",
    "narrative": "<3-4 sentence landing-page narrative; doesn't lead with the level word>",
    "drivers": [
      {"text": "<short driver phrase, ~10-15 words>",
       "chart_ids": ["<chart_id>", ...]}        // 1-3 charts per driver
    ]   // 3-5 drivers total per question
  },
  "financial_markets": {...same shape...}
}
```

The drivers' inline `chart_ids` render as small monospace anchor badges
next to each bullet — clicking jumps to the underlying chart on the
relevant page (auto-switching tabs if needed) and flashes a brief gold
highlight. This is the audit trail: every level decision is grounded
in specific charts the viewer can verify.

The level is the AI's judgement — see "Calibration philosophy" above.

**Display vs synthesizer-input split.** The page-level `summary` field
is deliberately tight (2-3 sentences cross-cutting synthesis) rather
than long-form: pages render the summary as a tl;dr above a collapsible
bullet-list of `key_findings`, which carry the structured detail and
chart citations. The synthesizer reads the full per-page output
(summary + key_findings + data_gaps + concern_score) so it has plenty
of substance to anchor on — the tightening only changes what the user
sees, not the synthesizer's diet. We chose this over a separate
"long for LLM, short for display" pair to avoid the cost of unrendered
LLM output and the risk of drift between the two summaries.

**Guardrails (shared across prompts):**

- Ground all assessments in observable data only; flag staleness and
  data gaps explicitly. Every claim must cite at least one chart_id.
- "I cannot judge X because the most recent data point is from Y" is
  preferred over inference.
- No counterfactual speculation beyond what the dashboard itself shows.
- No policy recommendations or historical-comparison claims.

**Page-level guardrails (additional):**

- **No internal-rubric leakage.** The page-level prompts include
  `concern_score` calibration anchors (e.g. "FX < ±3% → 0–25 score
  band"). These are scoring guidance for the AI, not market-recognised
  thresholds. Phrases like "below the X% major-concern threshold",
  "within the watchful band", "exceeds the moderate cutoff" are
  forbidden in the output — they leak internal mechanics the viewer
  has no context for.

**Singapore guardrails (specific):**

- **No MAS monetary-policy framing.** MAS conducts monetary policy via
  the SGD NEER policy band, not via a policy interest rate. SORA, MAS
  bills yields, OIS spreads, and interbank rates are endogenous to
  that framework — they reflect funding conditions, system liquidity,
  and global rates pass-through, not MAS policy levers. The Singapore
  prompt forbids describing these indicators as evidence of "monetary
  tightening" / "monetary easing" / "policy response" / "rate hikes".
  They are framed as funding-cost / liquidity-stress / interbank-market
  signals only. FX implied vol is framed as market-implied uncertainty,
  not policy expectations.

**Synthesizer guardrails (specific):**

- **FX phrasing precision.** When describing currency moves, name the
  currency that moved, not the pair. "USD/SGD" is a quote convention,
  not a subject. Wrong: "USD/SGD strengthened against the dollar" (the
  pair can't move against one of its constituents). Right: "the SGD
  strengthened 1.1% against the USD" or "USD/SGD fell 1.1% (SGD
  appreciation)".

### AI-disclosure footer (landing page)

A muted single-line strip below the status badges reads "✦ The analysis
above is AI-generated. Click to find out how →". Expanding it shows a
four-step plain-English methodology brief covering the deterministic
summary stats, per-page reads, synthesizer, and guardrails — followed by
an italic caveat: "AI can still be wrong. Treat the narratives as a
structured first read, not a final word — verify the key drivers via
the chart citations, especially before they leave the building."

### Stable chart IDs and anchor links

All chart `<canvas>` IDs follow `<page>.<tab>.<card_slug>` (see
Section 5 — "Stable, deterministic chart IDs"). The narrative cites
charts by ID (e.g. `sg.activity.petroleum_refining`); the rendered
expandable references are anchor links that scroll to and highlight the
target chart. A small monospace badge in each card header surfaces the
ID to the viewer so they can match the narrative reference visually.

### Per-page summaries

In addition to the landing-page status pills, each page (Global Shocks /
Singapore / Regional) renders the corresponding LLM-generated
page-level summary at the top — a compact card with the two
question-keyed observations for that page. Lets readers diving into a
specific page get the page-relevant story without navigating back to
the landing page.

### Implementation phases

1. ✅ **Stable chart IDs + visible badges** — `build_iran_monitor.py`
   emits deterministic `<page>.<tab>.[<panel>.]<card_slug>` IDs across
   214 charts; each card surfaces its ID as a quiet monospace badge in
   a footer with click-to-copy + URL-fragment-targeted highlight that
   auto-switches the containing tab if needed.
2. ✅ **Summary-stats extractor** — `scripts/compute_summary_stats.py`
   reads `data/chart_manifest.json` (emitted by the build) and queries
   the DB to produce `data/summary_stats.json` with per-series stats,
   shipping-pair stats, and a relevance index. 140 top-level charts /
   423 series at last count.
3. ✅ **Prompts** — four files in `prompts/`. Schema-strict, JSON-only,
   with the page-level scoring anchors and synthesizer calibration
   examples described above.
4. ✅ **Orchestrator** — `scripts/generate_narratives.py`. Loads
   prompts + per-page stats slice, calls Sonnet 4.6 four times,
   parses JSON, checkpoints after each successful page call (so
   network blips don't lose work), persists to
   `data/narratives.json` + the `metadata` table, saves trigger
   snapshot. Supports `--pages` for selective regeneration; loads
   missing page outputs from DB on synthesizer-only reruns.
5. ✅ **Renderer** — two section types in `page_layouts.py`:
   `status_indicators` (landing-page badges + narrative + collapsible
   Key Drivers with inline chart citations) and `page_summary`
   (top of each page: tight Overview + collapsible Key Drivers +
   collapsible Data Gaps). Plus `ai_methodology` footer on landing.
6. ✅ **Pipeline integration** — `scripts/energy/update_data.py` runs
   10 numbered steps end-to-end: 6 fetchers, 1st build, summary stats,
   trigger evaluation, narrative generation (gated), 2nd build. CLI
   flags: `--skip-narratives`, `--force-narratives`,
   `--show-trigger-state`.
7. ✅ **Trigger gating** — σ-based per-series thresholds computed from
   pre-war (2025) data; see "Trigger gating" below.

### Trigger gating

Steps 9 + 10 of the pipeline (narrative generation + final rebuild) are
skipped automatically when no curated trigger series has moved
meaningfully since the last narrative AND the last narrative is less
than 7 days old. Avoids burning $0.30–1.00 in API calls when nothing
material has moved.

**Trigger series.** A curated set of 15 series — the indicators most
frequently cited in narrative key findings:

- **Energy supply (7)**: Brent crude, naphtha SG, jet fuel NWE,
  petroleum refining IIP YoY, petrochemicals IIP YoY, PH CPI YoY,
  JKM LNG.
- **Financial markets (8)**: USD/SGD, SGD NEER, SGS 10Y yield,
  USD/SGD 1M implied vol, SORA 3M, PH 10Y yield, ID 10Y yield, gold.

Defined in `src/narrative_triggers_v2.py`.

**σ-based thresholds.** For each series, `scripts/compute_trigger_thresholds.py`
pulls 2025 (pre-war) data from the DB, computes σ of period-over-period
changes (weekly Δ for daily/weekly series, monthly Δ for monthly
series), and writes `data/trigger_thresholds.json` with the 2σ value
as each series's trigger threshold. Result: high-volatility series
(Brent, FX) get appropriately wide bands (Brent: 8.5%); low-volatility
series (CPI YoY, IIP YoY, ID 10Y) get appropriately tight ones
(ID 10Y: 13 bp). All series fire on the same statistical-significance
basis.

The 2σ band is calibrated to a calm year (2025); during the war regime
this may trigger more often. We accept this for the MVP — re-tune later
by editing `N_SIGMA` or computing thresholds over a wider window.

**Decision logic** (in `src/narrative_triggers_v2.py`):

A refresh fires if any of:

- A trigger series has moved more than its 2σ threshold since the last
  saved snapshot
- A trigger series has just entered or exited its `at_war_high` /
  `at_war_low` flag state (catches new extremes that didn't show up as
  a fast move)
- The last narrative is older than 7 days (sanity floor)
- No previous snapshot exists (first-ever run after the trigger system
  was rolled out — seed with `scripts/seed_trigger_snapshot.py` to
  avoid this)
- The user passed `--force-narratives`

The decision and reasons are printed at step 8b of `update_data.py`.
Inspect without committing to API spend with `--show-trigger-state`.

### Cost envelope

Sonnet 4.6 is ~$3 / Mtok input + $15 / Mtok output. A full narrative
refresh (3 page calls + 1 synthesizer) lands around **$0.30–1.00**
depending on the size of the page-level summary stats inputs. With
trigger gating active, expected cadence is ~1–2 refreshes per week
under typical war-period market conditions, so **$1–8 per month**.
Without gating (always-refresh on daily runs), would be $9–30 per
month.

### Files

| File | Purpose |
|---|---|
| `prompts/global_shocks.md` | Global Shocks page LLM prompt |
| `prompts/singapore.md` | Singapore page LLM prompt |
| `prompts/regional.md` | Regional page LLM prompt |
| `prompts/synthesizer.md` | Synthesizer LLM prompt (judgement-based) |
| `prompts/synthesizer.threshold-rules.md.bak` | Backup of the prior threshold-rules version |
| `scripts/compute_summary_stats.py` | Per-series stats extractor |
| `scripts/compute_trigger_thresholds.py` | σ-based threshold computer |
| `scripts/seed_trigger_snapshot.py` | One-shot snapshot seeder |
| `scripts/generate_narratives.py` | LLM orchestrator |
| `src/narrative_triggers_v2.py` | Trigger evaluation logic |
| `data/trigger_thresholds.json` | Committed σ-based thresholds |
| `data/summary_stats.json` | Latest summary stats (regenerated each run) |
| `data/narratives.json` | Latest narrative bundle (regenerated each run) |

---

## 8. Methodology highlights (for showcase)

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
