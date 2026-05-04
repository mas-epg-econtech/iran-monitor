# Iran Monitor

Internal MAS economic dashboard tracking developments related to the Iran war and Middle East situation. Surfaces global energy shocks, Singapore-domestic transmission, and regional spillovers in one place, with AI-generated narratives that summarise the read for an MAS audience.

Static-by-design: every refresh produces fresh `index.html` + 3 page HTMLs that can be served as plain files (currently deployed via GitHub Pages).

## Architecture at a glance

```
Iran Monitor/
  index.html, global_shocks.html, singapore.html, regional.html
                             ← regenerated end-to-end on every refresh
  data/
    iran_monitor.db          single source of truth (time series, trade, metadata)
    summary_stats.json       per-series stats — input to AI narratives
    narratives.json          last AI narrative bundle (also stashed in DB metadata)
    chart_manifest.json      emitted by the build, consumed by stats step
    trigger_thresholds.json  σ-based per-series thresholds for narrative gating
    portwatch/               raw IMF PortWatch CSVs (downloaded weekly)
    shipping/                computed nowcast outputs (STL+Ridge)
    controls/{fred,eia}/     static control variables for the nowcast Ridge regression
  src/
    db.py                    DB helper (single canonical iran_monitor.db)
    series_config.py         CEIC + financial-markets series registry
    page_layouts.py          page → section → card layout (renderer config)
    series_descriptions.py   friendly names + descriptions surfaced in card headers
    country_mapping.py       ISO-2 ↔ display-name + spotlight sets
    derived_series.py        derived-series computers (FX index, shares, rebases, etc.)
    narrative_triggers_v2.py σ-based trigger gate for narrative regeneration
  scripts/
    energy/update_data.py    main pipeline orchestrator (12 numbered steps)
    energy/financial_markets_fetchers.py   yfinance / ADB / investing.com fetchers
    shipping/download_portwatch_data.py    PortWatch ArcGIS API download
    shipping/nowcast_pipeline.py           STL+Ridge nowcast worker
    build_iran_monitor.py    static-HTML renderer for all 4 pages
    compute_summary_stats.py per-series stats extractor for AI narratives
    compute_trigger_thresholds.py  σ-based threshold computer (run once / annually)
    seed_trigger_snapshot.py one-shot seeder for the trigger gate
    generate_narratives.py   AI narrative orchestrator (4 Sonnet 4.6 calls)
  prompts/
    global_shocks.md         page-level AI prompt (energy supply only)
    singapore.md             page-level AI prompt (energy + financial markets)
    regional.md              page-level AI prompt (energy + financial markets)
    synthesizer.md           landing-page synthesizer AI prompt
  METHODOLOGY.md             full design + decision record
```

The dashboard is fully self-contained — no upstream-DB dependency, no VPS rsync. PortWatch data is downloaded directly from the public IMF ArcGIS API; shipping nowcast is computed locally; all other data comes from CEIC, Google Sheets (Bloomberg), SingStat, UN Comtrade, Motorist.sg, yfinance, ADB AsianBondsOnline, and investing.com — all wired into `update_data.py`.

## Refresh & build

Single command runs the whole pipeline (fetch → build → stats → narratives → rebuild):

```bash
python3.11 scripts/energy/update_data.py
```

CLI flags for partial runs:

| Flag | Effect |
|---|---|
| `--skip-narratives` | Skip steps 11-12 (no API spend); dashboard built with cached narratives |
| `--force-narratives` | Force narrative regeneration even if no triggers fired |
| `--show-trigger-state` | Run through stats + trigger evaluation, print decision, exit |
| `--skip-shipping-pipeline` | Skip steps 7-8 (no PortWatch download or nowcast compute) |
| `--force-shipping` | Force nowcast compute even if PortWatch brought no new data |

Data sources / refresh cadence:

| Source | Refresh cadence in pipeline |
|---|---|
| CEIC API (~95 series — energy, prices, sectoral activity, financial markets) | Every run, full refresh |
| Google Sheets (~37 series — Bloomberg refined products + financial markets) | Every run, full refresh |
| SingStat trade (Google Sheet — annual + monthly trade flows) | Every run, full refresh |
| UN Comtrade (regional dependence on SG, by SITC × partner) | Every run, incremental (only-stale by default) |
| SingStat Table Builder (construction contracts + electricity tariff) | Every run, full refresh |
| Motorist.sg (5 fuel grades) | Every run, full refresh |
| IMF PortWatch (daily ports + chokepoints CSVs) | Every run, incremental (publishes weekly Tue EST) |
| Shipping nowcast (STL+Ridge on PortWatch data) | Gated — only re-computes if PortWatch CSV brought new dates |
| AI narratives (4 × Sonnet 4.6 calls) | Gated — only refreshes if a curated trigger series has moved beyond its 2σ threshold OR last narrative is > 7 days old |

## AI narrative system

Four-call pipeline — Sonnet 4.6, temperature 0:

1. Three page-level reads (Global Shocks, Singapore, Regional) — each emits per-question concern_score + key_findings (with chart citations) + data_gaps
2. One synthesizer call — reads the page outputs and emits the landing-page status badges (Calm / Watchful / Strained / Critical), narratives, and per-driver chart citations

Cost per full refresh: ~$0.30–1.00. With trigger gating active, expected cadence is ~1–2 refreshes/week → **$1–8/month**.

See `METHODOLOGY.md` Section 7 for the full design (calibration philosophy, guardrails, trigger logic).

## Local development

After cloning, you'll need to recreate `data/iran_monitor.db` from a full pipeline run. Set `ANTHROPIC_API_KEY` in `.env` if you want narratives.

```bash
pip3.11 install -r requirements-pipeline.txt
python3.11 scripts/energy/update_data.py             # full run
python3.11 scripts/energy/update_data.py --skip-narratives   # dev iteration
```

Build only (no fetching):

```bash
python3.11 scripts/build_iran_monitor.py
```

## Deployment

Deploys to GitHub Pages at `https://mas-epg-econtech.github.io/iran-monitor/`. Auto-deploys on push to `main`. The Global Shocks page embeds the live shipping nowcast iframe from the sister site `https://mas-epg-econtech.github.io/shipping-nowcast/`.
