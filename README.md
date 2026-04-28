# Iran Monitor

Integrated dashboard tracking economic developments related to the Iran war and Middle East situation. Consolidates the work previously split across two precursor projects (the Middle East Energy Dashboard and the Shipping Nowcast) into a single user-facing product.

## Structure

```
Iran Monitor/
  data/
    dashboard.db              Energy + SG indicators (copy of Middle East Dashboard's SQLite)
    asean_markets.db          Regional financial markets (copy of asean-dashboard's SQLite)
    shipping/
      nowcast_results_s13.json    Pulled from VPS shipping pipeline outputs
      crisis_deviation_summary.csv
  src/
    db.py                     Energy DB helper
    charts.py                 Chart-rendering helpers (Plotly)
    transforms.py             Data transforms
    series_config.py          Energy series registry
    dependency_config.py      Energy supply-chain transmission graph
    narrative_prompt.py       LLM narrative prompt template
    narrative_triggers.py     Narrative regeneration trigger logic
    page_layouts.py           NEW (TBD) — maps data slices to page sections
  scripts/
    refresh_data.py           NEW (TBD) — orchestrator: copies upstream DBs/JSONs into data/
    build_iran_monitor.py     NEW (TBD) — builds all 4 HTML pages
    energy/                   Copies of Middle East Dashboard ingestion scripts
    shipping/                 Copies of shipping nowcast pipeline scripts (from VPS)
    markets/                  Copies of asean-dashboard ingestion scripts (from VPS)
  assets/
    styles.css                NEW (TBD) — shared dashboard chrome
    flags/                    NEW (TBD) — SVG country flags for MAS report cards
  reference/
    asean_dashboard_reference.html       Original asean-dashboard layout, for reference
    shipping_nowcast_reference.html      Original shipping nowcast dashboard, for reference
  _vps_pull/                  Staging area for files pulled from VPS via rsync (gitignored)
```

## Build pages

- `index.html`            Landing — narrative card + 3 nav cards
- `global_shocks.html`    Global energy prices + shipping (tabbed)
- `singapore.html`        SG domestic prices, sectoral activity, + 3 placeholder sections
- `regional.html`         Regional financial markets, MAS EPG report cards, + 3 placeholder sections

## Data sources

This project does NOT modify the precursor folders (`Middle East Dashboard/`, `Forecasting/`). Iran Monitor copies what it needs from them and operates from its own copies.

| Data | Origin | Refresh |
|---|---|---|
| Energy/SG time series + trade | `Middle East Dashboard/data/dashboard.db` | Manual (run `update_data.py` in ME Dashboard, then `scripts/refresh_data.py` here) |
| Shipping nowcast outputs | VPS `/opt/shipping-nowcast-pipeline/outputs/nowcast/` | Pulled via rsync into `_vps_pull/`, then copied into `data/shipping/` by `refresh_data.py` |
| Regional markets (FX, bonds, commodities) | VPS `/opt/asean-dashboard/data/dashboard.db` | Pulled via rsync into `_vps_pull/`, then copied into `data/asean_markets.db` |
| MAS EPG report PDFs | SharePoint links | Static — defined in `src/page_layouts.py` |

## Local development

All development is local. VPS deployment is a future step.

```bash
# Refresh local data from upstream sources
python3 scripts/refresh_data.py

# Rebuild all 4 HTML pages
python3 scripts/build_iran_monitor.py

# Open in browser
open index.html
```

## VPS pull command (re-run to refresh shipping data)

```bash
rsync -avz --progress \
  --exclude='__pycache__/' --exclude='*.tmp' --exclude='.DS_Store' \
  --exclude='*_test*.json' --exclude='venv/' --exclude='logs/' \
  --exclude='shipping-nowcast/' \
  root@204.168.224.154:/opt/shipping-nowcast-pipeline/ \
  "_vps_pull/shipping-nowcast-pipeline/"

rsync -avz --progress \
  --exclude='__pycache__/' --exclude='*.tmp' --exclude='.DS_Store' \
  --exclude='venv/' --exclude='logs/' --exclude='node_modules/' --exclude='.git/' \
  root@204.168.224.154:/opt/asean-dashboard/ \
  "_vps_pull/asean-dashboard/"
```

## Eventual deployment

Will deploy to a new GitHub Pages sister site (e.g. `mas-epg-econtech.github.io/iran-monitor/`) running on the existing Hetzner VPS, alongside the shipping nowcast and (eventually migrated) ME Dashboard pipelines. Cron orchestration TBD when we cut over.
