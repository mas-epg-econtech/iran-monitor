"""
Page layout configuration for Iran Monitor.

Defines the structure of each dashboard page — what sections appear, in what
order, and what data each section pulls from. The renderer reads this config
and produces the corresponding HTML.

Section types:
  chart_grid       — render a grid of charts, one per node from dependency_config
                     (or one per direct series_id reference)
  shipping_iframe  — embed an external dashboard via <iframe>
  pdf_cards        — render cards linking to PDF reports (with SVG country flags)
  placeholder      — render a "Coming soon" card listing planned content
  narrative        — render the Key Takeaways panel (LLM-generated or placeholder)

Each page also has a "narrative_source" controlling where its narrative comes
from: 'metadata.llm_narrative' pulls from iran_monitor.db's metadata table,
'placeholder' renders generic placeholder text.
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Cross-page navigation (the chrome's nav bar + landing page card targets)
# ---------------------------------------------------------------------------
PAGE_NAV = [
    {"slug": "index",          "label": "Home",            "file": "index.html"},
    {"slug": "global_shocks",  "label": "Global Shocks",   "file": "global_shocks.html"},
    {"slug": "singapore",      "label": "Singapore",       "file": "singapore.html"},
    {"slug": "regional",       "label": "Regional",        "file": "regional.html"},
]


# ---------------------------------------------------------------------------
# Landing page nav cards (shown on index.html)
# ---------------------------------------------------------------------------
LANDING_CARDS = [
    {
        "slug": "global_shocks",
        "title": "Global Shocks",
        "description": "Global energy prices and shipping conditions affecting trade flows worldwide.",
    },
    {
        "slug": "singapore",
        "title": "Singapore",
        "description": "Domestic prices, sectoral activity, and economic indicators for Singapore.",
    },
    {
        "slug": "regional",
        "title": "Regional",
        "description": "Asia financial markets, MAS EPG country reports, and regional indicators across Asia ex-Singapore.",
    },
]


# ---------------------------------------------------------------------------
# Page definitions
# ---------------------------------------------------------------------------
PAGES = {

    # ── Landing ───────────────────────────────────────────────────────────
    "index": {
        "title": "Iran Monitor",
        "subtitle": "Economic developments related to the Iran war and Middle East situation",
        "narrative_source": "placeholder",
        "narrative_placeholder": (
            "Key takeaways across Global Shocks, Singapore, and Regional dashboards "
            "will appear here once the LLM narrative trigger system is wired in."
        ),
        "sections": [
            {"type": "landing_cards"},  # Special section; consumes LANDING_CARDS
        ],
    },

    # ── Global Shocks ─────────────────────────────────────────────────────
    "global_shocks": {
        "title": "Global Shocks",
        "subtitle": "Energy prices and shipping flow disruption from the Iran/Hormuz crisis",
        "narrative_source": "placeholder",
        "narrative_placeholder": (
            "Global energy and shipping takeaways will appear here once narrative "
            "regeneration triggers are configured."
        ),
        "sections": [
            {
                "type": "tab_group",
                "tabs": [
                    {
                        "slug": "energy",
                        "label": "Energy",
                        "subsections": [
                            {
                                "type": "chart_grid",
                                "title": "Upstream commodities",
                                "description": (
                                    "Global benchmark prices for crude oil and natural gas — the "
                                    "primary channels through which an Iran/Hormuz disruption "
                                    "transmits price shocks downstream."
                                ),
                                "nodes": ["crude_oil", "natural_gas"],
                            },
                            {
                                "type": "chart_grid",
                                "title": "Refined products",
                                "description": (
                                    "Spot prices for refined fuels — marine bunker, jet fuel, "
                                    "diesel/gasoline, naphtha, and LPG. These respond to crude "
                                    "with a lag and varying passthrough."
                                ),
                                "nodes": ["marine_fuel", "jet_fuel", "diesel_petrol", "naphtha", "lpg"],
                            },
                            {
                                "type": "chart_grid",
                                "title": "Industrial inputs",
                                "description": (
                                    "Petrochemicals (ethylene, polyethylene varieties) and "
                                    "fertilisers (urea) — derived from crude/gas; final inputs "
                                    "to manufacturing and agriculture sectors."
                                ),
                                "nodes": ["olefins_ethylene", "olefins_polymers", "fertilisers"],
                            },
                        ],
                    },
                    {
                        "slug": "shipping",
                        "label": "Shipping",
                        "subsections": [
                            {
                                "type": "shipping_iframe",
                                "title": "Hormuz shipping nowcast",
                                "description": (
                                    "Live shipping nowcast dashboard, hosted separately. Tracks "
                                    "actual versus counterfactual vessel flows across 5 chokepoints "
                                    "and regional aggregates using IMF PortWatch satellite data."
                                ),
                                "url": "https://mas-epg-econtech.github.io/shipping-nowcast/",
                            },
                        ],
                    },
                ],
            },
        ],
    },

    # ── Singapore ─────────────────────────────────────────────────────────
    "singapore": {
        "title": "Singapore",
        "subtitle": "Domestic price transmission and sectoral activity in the Singapore economy",
        "narrative_source": "metadata.llm_narrative",
        "narrative_placeholder": (
            "Singapore-specific takeaways will appear here once the narrative trigger "
            "system is wired in."
        ),
        "sections": [
            {
                "type": "tab_group",
                "tabs": [
                    {
                        "slug": "prices",
                        "label": "Prices",
                        "subsections": [
                            {
                                "type": "chart_grid",
                                "title": "Prices",
                                "description": (
                                    "Singapore retail fuel prices, headline and core inflation, plus the "
                                    "domestic supply / import / export / producer price indices that capture "
                                    "where energy cost shocks are showing up in the price level."
                                ),
                                "nodes": [
                                    # Retail fuel — split into SingStat (monthly) and Motorist (daily)
                                    # for cleaner reading; original land_transport node combined them.
                                    {
                                        "label": "SG retail fuel prices (SingStat monthly)",
                                        "description": "Monthly retail prices for petrol grades and diesel from SingStat.",
                                        "series": [
                                            "singstat_petrol_92",
                                            "singstat_petrol_95",
                                            "singstat_petrol_98",
                                            "singstat_diesel",
                                        ],
                                    },
                                    {
                                        "label": "SG pump prices (Motorist daily)",
                                        "description": "Daily pump prices scraped from Motorist.sg across grades and brands.",
                                        "series": [
                                            "motorist_92",
                                            "motorist_95",
                                            "motorist_98",
                                            "motorist_premium",
                                            "motorist_diesel",
                                        ],
                                    },
                                    "gas_electricity",       # Electricity tariff (moved up — sits naturally with the other consumer-facing energy prices)
                                    "sg_cpi",                # CPI YoY/MoM + MAS core
                                    "sg_supply_prices",      # Domestic supply price indices (oil/non-oil)
                                    "sg_import_prices",      # IPI oil/non-oil/food
                                    "sg_export_prices",      # EPI oil/non-oil
                                    "sg_producer_prices",    # MPPI oil/non-oil
                                ],
                            },
                        ],
                    },
                    {
                        "slug": "sectoral_activity",
                        "label": "Sectoral activity",
                        "subsections": [
                            {
                                "type": "chart_grid",
                                "title": "Sectoral economic activity",
                                "description": (
                                    "Real-side activity indicators across the sectors most exposed to upstream "
                                    "energy cost shocks: petroleum refining, petrochemicals, basic chemicals, "
                                    "wholesale (bunkering and ex-bunkering), construction, real estate, and F&B."
                                ),
                                "nodes": [
                                    # Petroleum refining — split production vs trade so the trade
                                    # chart gets a meaningful title (was "— SGD Thousand").
                                    {
                                        "label": "Petroleum refining",
                                        "description": "Refinery output — directly affected by crude oil costs and margins.",
                                        "series": ["ipi_petroleum"],
                                    },
                                    {
                                        "label": "Petroleum refining - imports and exports",
                                        "description": "Singapore's monthly petroleum trade values (SingStat).",
                                        "series": ["singstat_imports_petroleum", "singstat_exports_petroleum"],
                                    },
                                    "petrochemicals",
                                    "basic_chemicals",
                                    "wholesale_bunkering",
                                    "wholesale_ex_bunkering",
                                    "construction",
                                    "real_estate",
                                    "food_beverage",
                                    "water_transport",       # SG-relevant: container throughput, sea cargo
                                    "air_transport",         # Air freight movements
                                    # Land transport activity — moved here from Domestic prices
                                    # (visitor arrivals by land is an activity proxy, not a price).
                                    {
                                        "label": "Land transport activity",
                                        "description": "Visitor arrivals by land — proxy for cross-border road movement.",
                                        "series": ["visitor_arrival_land"],
                                    },
                                ],
                            },
                        ],
                    },
                    {
                        "slug": "trade",
                        "label": "Trade",
                        "subsections": [
                            {
                                "type": "placeholder",
                                "title": "Trade",
                                "planned_content": [
                                    "SG petroleum trade by partner country (Comtrade)",
                                    "Total trade (NODX, NORX)",
                                    "Container throughput trends",
                                    "Bilateral exposure to ME-linked partners",
                                ],
                            },
                        ],
                    },
                    {
                        "slug": "shipping",
                        "label": "Shipping",
                        "subsections": [
                            {
                                "type": "placeholder",
                                "title": "Shipping",
                                "planned_content": [
                                    "Malacca chokepoint vessel transits (actual vs counterfactual)",
                                    "Singapore port (PSA, Jurong, Tuas) call volumes",
                                    "SE Asian-Oceania regional shipping aggregate",
                                    "Bunkering-related vessel flow indicators",
                                ],
                            },
                        ],
                    },
                    {
                        "slug": "financial_markets",
                        "label": "Financial markets",
                        "subsections": [
                            {
                                "type": "placeholder",
                                "title": "Financial markets",
                                "planned_content": [
                                    "MAS Yield 2Y, 10Y",
                                    "SORA 3M compounded",
                                    "SGX daily turnover",
                                    "Forex monthly turnover",
                                ],
                            },
                        ],
                    },
                ],
            },
        ],
    },

    # ── Regional ──────────────────────────────────────────────────────────
    "regional": {
        "title": "Regional",
        "subtitle": "Asian economies exposed to Middle East stress: financial markets and country-level monitoring",
        "narrative_source": "placeholder",
        "narrative_placeholder": (
            "Regional takeaways will appear here once narrative regeneration is wired in."
        ),
        "sections": [
            {
                "type": "tab_group",
                "tabs": [
                    {
                        "slug": "prices",
                        "label": "Prices",
                        "subsections": [
                            {
                                "type": "chart_grid",
                                "title": "Regional consumer prices",
                                "description": (
                                    "Year-on-year inflation across 10 Asian economies "
                                    "(China, India, Indonesia, Japan, Malaysia, Philippines, "
                                    "South Korea, Taiwan, Thailand, Vietnam). Headline CPI "
                                    "captures the broadest pass-through of the Iran/Hormuz "
                                    "energy shock; core CPI strips out food and energy to "
                                    "show second-round effects."
                                ),
                                "nodes": [
                                    "regional_cpi_headline",
                                    "regional_cpi_core",
                                ],
                            },
                        ],
                    },
                    {
                        "slug": "sectoral_activity",
                        "label": "Sectoral activity",
                        "subsections": [
                            {
                                "type": "chart_grid",
                                "title": "Regional industrial production",
                                "description": (
                                    "Industrial / manufacturing production indices for 10 "
                                    "Asian economies — real-side activity gauges that reveal "
                                    "where higher energy and input costs are biting into "
                                    "manufacturing output. Each country's index uses its own "
                                    "national base year; the level differences across panels "
                                    "are not directly comparable."
                                ),
                                "nodes": [
                                    {"label": "China",       "description": "China industrial production index (NBS) — output across mining, manufacturing, and utilities.",       "series": ["regional_ipi_cn"]},
                                    {"label": "India",       "description": "India index of industrial production (MoSPI) — output across mining, manufacturing, and electricity.", "series": ["regional_ipi_in"]},
                                    {"label": "Indonesia",   "description": "Indonesia large & medium manufacturing production index (BPS).",                                       "series": ["regional_ipi_id"]},
                                    {"label": "Japan",       "description": "Japan mining & manufacturing production index (METI).",                                                "series": ["regional_ipi_jp"]},
                                    {"label": "Malaysia",    "description": "Malaysia industrial production index (DOSM) — mining, manufacturing, and electricity.",               "series": ["regional_ipi_my"]},
                                    {"label": "Philippines", "description": "Philippines volume of production index for manufacturing (PSA).",                                      "series": ["regional_ipi_ph"]},
                                    {"label": "South Korea", "description": "South Korea all-industry production index (KOSTAT) — broad activity gauge.",                            "series": ["regional_ipi_kr"]},
                                    {"label": "Taiwan",      "description": "Taiwan industrial production index (MOEA) — mining, manufacturing, and utilities.",                    "series": ["regional_ipi_tw"]},
                                    {"label": "Thailand",    "description": "Thailand value-added manufacturing production index (OIE).",                                            "series": ["regional_ipi_th"]},
                                    {"label": "Vietnam",     "description": "Vietnam industrial production index (GSO) — mining, manufacturing, electricity, and water.",          "series": ["regional_ipi_vn"]},
                                ],
                            },
                        ],
                    },
                    {
                        "slug": "trade",
                        "label": "Trade",
                        "subsections": [
                            {
                                "type": "placeholder",
                                "title": "Trade",
                                "planned_content": [
                                    "Regional petroleum trade flows",
                                    "Bilateral trade exposure to ME / Iran",
                                    "Container throughput at major Asian ports",
                                ],
                            },
                        ],
                    },
                    {
                        "slug": "shipping",
                        "label": "Shipping",
                        "subsections": [
                            {
                                "type": "placeholder",
                                "title": "Shipping",
                                "planned_content": [
                                    "East Asian / SE Asian / Indian Subcontinent regional aggregates (PortWatch)",
                                    "Country-level shipping flow data for India, Japan, Korea, Taiwan, Philippines, ASEAN composite",
                                    "Major Asian port call volumes (Busan, Tokyo, Shanghai, Mumbai, Manila, Kaohsiung, etc.)",
                                ],
                            },
                        ],
                    },
                    {
                        "slug": "financial_markets",
                        "label": "Financial markets",
                        "subsections": [
                            {
                                "type": "chart_grid",
                                "title": "Financial markets",
                                "description": (
                                    "ASEAN currency, sovereign bond, and commodity benchmarks. FX from yfinance "
                                    "(IDR, MYR, PHP, THB, VND); 10-year sovereign yields from ADB AsianBondsOnline; "
                                    "key commodities (Brent, JKM LNG, Newcastle coal, palm oil, rubber, nickel, gold) "
                                    "from yfinance and Investing.com."
                                ),
                                "series_groups": [
                                    ("FX (per USD)", ["IDR", "MYR", "PHP", "THB", "VND"]),
                                    ("10-Year Sovereign Yields (%)", ["US_10Y", "ID_10Y", "MY_10Y", "PH_10Y", "TH_10Y"]),
                                    # Each commodity gets its own chart — they're in different units
                                    # and conceptually unrelated (oil vs LNG vs coal vs metals etc.).
                                    ("Brent crude oil", ["BRENT"]),
                                    ("JKM LNG", ["JKM_LNG"]),
                                    ("Newcastle coal", ["COAL_NEWC"]),
                                    ("Crude palm oil", ["CPO"]),
                                    ("Rubber TSR20", ["RUBBER_TSR20"]),
                                    ("Nickel", ["NICKEL"]),
                                    ("Gold", ["GOLD"]),
                                ],
                            },
                        ],
                    },
                    {
                        "slug": "mas_epg_reports",
                        "label": "MAS EPG reports",
                        "subsections": [
                            {
                                "type": "pdf_cards",
                                "title": "MAS EPG reports",
                                "description": "",
                                "series_intro": {
                                    "title": "Middle East Faultline Watch",
                                    "body": (
                                        "ME Faultline Watch (\u201CThe Watch\u201D) is a joint initiative by IED and "
                                        "FMS to identify countries most exposed to energy and/or financial stress "
                                        "arising from the Middle East conflict. The Watch focuses on economies with "
                                        "the weakest links\u2014those facing heightened external spillovers amid "
                                        "limited energy and financial buffers\u2014where shocks from higher energy "
                                        "prices, tighter financial conditions, or disrupted flows are most likely "
                                        "to translate into macro-financial vulnerabilities."
                                    ),
                                },
                                "reports": [
                                    {
                                        "country": "Philippines",
                                        "iso": "PH",
                                        "date": "2026-03-23",
                                        "title": "ME Faultline Watch — Philippines",
                                        "url": "https://team.dms.mas.gov.sg/sites/EPG_IED/2.2 Regular Outputs/ME Watch/1_ME Faultline Watch - Philippines (23 March 2026).pdf",
                                    },
                                    {
                                        "country": "India",
                                        "iso": "IN",
                                        "date": "2026-04-02",
                                        "title": "ME Faultline Watch — India",
                                        "url": "https://team.dms.mas.gov.sg/sites/EPG_IED/2.2 Regular Outputs/ME Watch/2_ME Faultline Watch - India (2 April 2026).pdf",
                                    },
                                    {
                                        "country": "Japan",
                                        "iso": "JP",
                                        "date": "2026-04-09",
                                        "title": "ME Faultline Watch — Japan",
                                        "url": "https://team.dms.mas.gov.sg/sites/EPG_IED/2.2 Regular Outputs/ME Watch/3_ME Faultline Watch - Japan (9 April 2026).pdf",
                                    },
                                    {
                                        "country": "ASEAN",
                                        "iso": "ASEAN",
                                        "date": "2026-04-09",
                                        "title": "ME Faultline Watch — ASEAN",
                                        "url": "https://team.dms.mas.gov.sg/sites/EPG_IED/2.2 Regular Outputs/ME Watch/4_ME Faultline Watch - ASEAN (9 April 2026).pdf",
                                    },
                                    {
                                        "country": "Korea",
                                        "iso": "KR",
                                        "date": "2026-04-17",
                                        "title": "ME Faultline Watch — Korea",
                                        "url": "https://team.dms.mas.gov.sg/sites/EPG_IED/2.2 Regular Outputs/ME Watch/5_ME Faultline Watch - Korea (17 April 2026).pdf",
                                    },
                                    {
                                        "country": "Taiwan",
                                        "iso": "TW",
                                        "date": "2026-04-20",
                                        "title": "ME Faultline Watch — Taiwan",
                                        "url": "https://team.dms.mas.gov.sg/sites/EPG_IED/2.2 Regular Outputs/ME Watch/6_ME Faultline Watch - Taiwan (20 April 2026).pdf",
                                    },
                                ],
                            },
                        ],
                    },
                ],
            },
        ],
    },
}
