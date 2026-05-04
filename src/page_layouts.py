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
# Helpers shared by the Singapore Trade Exposure tab — generate the two
# sub-chart configs (annual ME shares + monthly stacked levels) for a given
# SITC code. Keeps the page_layouts.PAGES dict readable.
# ---------------------------------------------------------------------------
_ME_SPOTLIGHT = ("ae", "sa", "qa", "kw", "iq", "om")


def _SG_TRADE_SUBCHARTS(sitc: str) -> list[dict]:
    """Return the subcharts list for one SITC's combined card.

    Annual shares chart shows ME-spotlight countries only (no Others
    residual — bar height naturally caps at the total ME share). Monthly
    levels chart includes Others so each bar's stack equals SG's total
    monthly imports of that SITC.
    """
    return [
        {
            "subtitle":     "Annual shares (2023–2025)",
            "chart_type":   "bar",
            "x_axis_type":  "category",
            "stacked":      True,
            "series": [f"sg_imp_share_sitc_{sitc}_{c}" for c in _ME_SPOTLIGHT],
        },
        {
            "subtitle":     "Monthly levels",
            "chart_type":   "bar",
            "x_axis_type":  "category",
            "stacked":      True,
            "series": [f"sg_imp_monthly_sitc_{sitc}_{c}" for c in _ME_SPOTLIGHT]
                      + [f"sg_imp_monthly_sitc_{sitc}_others"],
        },
    ]


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
            # 4-color status badges + narrative + drivers + expandable refs.
            # Pulls from `narrative_synthesizer` in metadata; gracefully
            # falls back to a placeholder when the pipeline hasn't run.
            {"type": "status_indicators"},
            # AI-disclosure + methodology footer (collapsible). Sits at the
            # bottom of the landing page so viewers can see how the AI
            # narrative + status badges above were produced.
            {"type": "ai_methodology"},
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
            # LLM-generated tight summary + key_findings bullets at the top.
            # Reads `narrative_global_shocks` from metadata; silent skip when
            # the pipeline hasn't run.
            {"type": "page_summary"},
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
            # LLM-generated tight summary + key_findings bullets per question
            # (energy_supply + financial_markets), at the top of the page.
            {"type": "page_summary"},
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
                                    {
                                        "label": "Retail fuel prices (monthly)",
                                        "description": "Monthly retail prices for the three petrol grades plus diesel — official SingStat survey series. Direct passthrough from upstream crude and refined-product price moves.",
                                        "series": [
                                            "singstat_petrol_92",
                                            "singstat_petrol_95",
                                            "singstat_petrol_98",
                                            "singstat_diesel",
                                        ],
                                    },
                                    {
                                        "label": "Pump prices (daily)",
                                        "description": "Daily pump-station prices scraped across grades and brands. Higher-frequency complement to the monthly survey above; useful for catching rapid passthrough during oil-price shocks.",
                                        "series": [
                                            "motorist_92",
                                            "motorist_95",
                                            "motorist_98",
                                            "motorist_premium",
                                            "motorist_diesel",
                                        ],
                                    },
                                    {
                                        "label": "Electricity tariff (households)",
                                        "description": "Low-tension domestic tariff. Singapore power runs almost entirely on imported gas, so this tracks LNG and pipeline-gas prices with a lag — the household-facing channel for Middle East gas disruption.",
                                        "series": ["singstat_electricity_tariff"],
                                    },
                                    {
                                        "label": "Headline and core CPI (year-on-year)",
                                        "description": "Year-on-year change in headline CPI and MAS Core inflation (which strips out accommodation and private-transport costs). Broadest measure of how energy and imported-input cost shocks reach households.",
                                        "series": ["ceic_cpi_yoy", "ceic_mas_core_inflation"],
                                    },
                                    {
                                        "label": "Headline and core CPI (month-on-month)",
                                        "description": "Same headline and core inflation series, month-on-month — captures price-momentum shifts that the year-on-year series smooths over.",
                                        "series": ["ceic_cpi_mom", "mas_core_inflation_mom"],
                                    },
                                    "sg_supply_prices",      # Domestic supply price indices (oil/non-oil)
                                    "sg_import_prices",      # Import price indices (oil/non-oil/food)
                                    "sg_export_prices",      # Export price indices (oil/non-oil)
                                    "sg_producer_prices",    # Manufactured-producers' price indices (oil/non-oil)
                                    "construction_prices",   # Construction materials prices
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
                                    "energy cost shocks: refining/petrochemicals, wholesale, transport, "
                                    "construction, real estate, and F&B."
                                ),
                                "nodes": [
                                    # ── Refining & chemicals (production) ──
                                    {
                                        "label": "Petroleum refining",
                                        "description": "Index of industrial production for refinery throughput. Directly hit by crude-oil cost shocks — a key transmission channel for Middle East disruption into downstream chemicals and bunker fuels.",
                                        "series": ["ipi_petroleum"],
                                    },
                                    {
                                        "label": "Petrochemicals",
                                        "description": "Industrial production for the Jurong Island petrochemicals complex. Naphtha and LPG feedstocks are highly sensitive to Middle East crude flows — cracker margins compress quickly when feedstock prices spike.",
                                        "series": ["ipi_petrochemicals"],
                                    },
                                    {
                                        "label": "Specialty and other chemicals",
                                        "description": "Industrial production for specialty (paints, coatings, adhesives) and other basic chemicals. Both downstream of crude/naphtha — capture feedstock cost pressure through the chemicals chain.",
                                        "series": ["ipi_specialty_chemicals", "ipi_other_chemicals"],
                                    },
                                    {
                                        "label": "Wholesale trade",
                                        "description": "Foreign Wholesale Trade Index — overall plus petroleum, chemicals, and ship-chandlers/bunkering subsectors. Direct gauge of how upstream cost shocks pass through to wholesale activity at the Port of Singapore.",
                                        "series": [
                                            "fwti_overall",
                                            "fwti_petroleum",
                                            "fwti_chemical",
                                            "fwti_bunkering",
                                        ],
                                    },
                                    # ── Transport (Jan-2025 min date applied via data_min_date) ──
                                    {
                                        "label": "Sea cargo handled",
                                        "description": "Total sea cargo handled at the Port of Singapore (thousand tons). Volume signal for seaborne trade flows through the Strait of Singapore — sensitive to bunker-fuel costs and any rerouting around Hormuz.",
                                        "series": ["sea_cargo_handled"],
                                        "data_min_date": "2025-01-01",
                                    },
                                    {
                                        "label": "Container throughput",
                                        "description": "Container throughput at Singapore port (thousand TEU). Real-time gauge of containerised trade flow — captures the broader downstream impact of energy-price shocks on global supply chains.",
                                        "series": ["container_throughput"],
                                        "data_min_date": "2025-01-01",
                                    },
                                    {
                                        "label": "Changi Airport flight movements",
                                        "description": "Monthly count of aircraft movements at Changi. Sensitive to jet-fuel cost shocks via airline capacity decisions and to broader travel-demand impacts of regional conflict.",
                                        "series": ["air_flight_movements"],
                                        "data_min_date": "2025-01-01",
                                    },
                                    {
                                        "label": "Changi Airport passenger movements",
                                        "description": "Monthly passenger throughput at Changi. Tracks the consumer-travel side of aviation demand — a leading signal for regional service-sector activity.",
                                        "series": ["air_passenger_movements"],
                                        "data_min_date": "2025-01-01",
                                    },
                                    {
                                        "label": "Changi Airport air freight",
                                        "description": "Monthly air-freight tonnage handled at Changi. High-value, time-sensitive cargo channel — first place jet-fuel cost spikes show up in shipping logistics.",
                                        "series": ["air_freight_movements"],
                                        "data_min_date": "2025-01-01",
                                    },
                                    {
                                        "label": "Cross-border land arrivals",
                                        "description": "Visitor arrivals into Singapore by land. Proxy for road-transport activity across the Causeway and Second Link — sensitive to retail-fuel cost moves and broader regional travel demand.",
                                        "series": ["visitor_arrival_land"],
                                        "data_min_date": "2025-01-01",
                                    },
                                    # ── Downstream ──
                                    {
                                        "label": "Construction contracts awarded",
                                        "description": "Monthly value of contracts awarded, public and private. Leading indicator of the building-project pipeline; slow to react to cost shocks since procurement reflects locked-in input prices.",
                                        "series": ["singstat_construction_contracts"],
                                    },
                                    {
                                        "label": "Construction material demand",
                                        "description": "Monthly physical-volume demand for cement, steel bars, and granite. Cement and steel are energy-intensive to produce, so their demand reflects how upstream cost pressure feeds into building activity.",
                                        "series": [
                                            "ceic_constr_demand_cement",
                                            "ceic_constr_demand_steel",
                                            "ceic_constr_demand_granite",
                                        ],
                                    },
                                    {
                                        "label": "Private property price index",
                                        "description": "URA quarterly benchmark for non-HDB housing prices. Slow-moving channel for input-cost pressure via construction and utility costs; useful for spotting whether upstream shocks are reaching property markets.",
                                        "series": ["ceic_property_price_index"],
                                    },
                                    {
                                        "label": "Property deals (developer sales + resales)",
                                        "description": "URA monthly count of private residential transactions. Higher-frequency proxy for buyer activity than the price index; sensitive to broader risk sentiment during conflict episodes.",
                                        "series": ["ceic_residential_transactions"],
                                    },
                                    {
                                        "label": "Food and beverage services",
                                        "description": "F&B Services Index — overall plus five segments (restaurants, fast food, caterers, food courts, cafes). Tracks how imported food-input cost pressure reaches consumer-facing F&B.",
                                        "series": [
                                            "fb_overall",
                                            "fb_restaurants",
                                            "fb_fast_food",
                                            "fb_caterers",
                                            "fb_food_courts",
                                            "fb_cafes",
                                        ],
                                        "data_min_date": "2025-01-01",
                                    },
                                ],
                            },
                        ],
                    },
                    {
                        "slug": "trade",
                        "label": "Trade Exposure",
                        "hide_date_range": True,    # bar charts; zoom selector irrelevant
                        "subsections": [
                            # ── Mineral fuel imports — Middle East exposure by SITC
                            # One wide card per SITC. Each card has two
                            # side-by-side sub-charts: annual ME shares
                            # (left, bars NOT summing to 100% — each
                            # segment is a single ME-spotlight country's %)
                            # and monthly stacked levels (right, bars stack
                            # to SG total).
                            {
                                "type": "chart_grid",
                                "title": "Mineral fuel imports — Middle East exposure by category",
                                "description": (
                                    "How dependent Singapore is on Middle East suppliers — UAE, "
                                    "Saudi Arabia, Qatar, Kuwait, Iraq, and Oman — for each mineral-fuel "
                                    "category. Iran does not appear in the data because of sanctions. Each "
                                    "card pairs annual Middle East import shares (left) with monthly stacked "
                                    "import levels (right)."
                                ),
                                "columns": 1,    # one wide card per row
                                "single_legend": True,   # one legend per card across left+right charts
                                "nodes": [
                                    {
                                        "label": "Mineral fuels — chapter total",
                                        "description": "SITC 3 — all mineral fuels and related materials (crude, refined products, gas, coal, electric current). Headline measure of Singapore's overall fossil-fuel import dependence.",
                                        "subcharts": _SG_TRADE_SUBCHARTS("3"),
                                    },
                                    {
                                        "label": "Crude petroleum oils",
                                        "description": "SITC 333 — unrefined crude oil, feedstock for Singapore's Jurong Island refineries (processed into gasoline, diesel, jet fuel, naphtha). Most directly exposed category to Middle East supply disruption.",
                                        "subcharts": _SG_TRADE_SUBCHARTS("333"),
                                    },
                                    {
                                        "label": "Refined petroleum products",
                                        "description": "SITC 334 — already-refined fuels (gasoline, diesel, jet fuel, naphtha, fuel oil). Singapore also imports refined products to blend, re-export, and supply bunker fuel — the trading-hub side of refining activity.",
                                        "subcharts": _SG_TRADE_SUBCHARTS("334"),
                                    },
                                    {
                                        "label": "Natural gas (all forms)",
                                        "description": "SITC 343 — natural gas in both pipeline and liquefied form. Singapore is almost entirely import-dependent for gas, which fuels nearly all power generation. Qatar dominates regional LNG supply.",
                                        "subcharts": _SG_TRADE_SUBCHARTS("343"),
                                    },
                                    {
                                        "label": "Naphtha",
                                        "description": "SITC 3346043 — naphtha, cracked into ethylene/propylene for plastics and used as a gasoline blendstock. Singapore is a major regional trading hub with key Middle Eastern suppliers.",
                                        "subcharts": _SG_TRADE_SUBCHARTS("3346043"),
                                    },
                                    {
                                        "label": "Liquefied natural gas (LNG)",
                                        "description": "SITC 3431 — LNG specifically (vs SITC 3432 pipeline gas). Imported into the SLNG terminal on Jurong Island; Qatar dominates Middle Eastern supply and is critical to Singapore's power-sector fuel.",
                                        "subcharts": _SG_TRADE_SUBCHARTS("3431000"),
                                    },
                                ],
                            },
                            {
                                "type": "chart_grid",
                                "title": "Industrial chemical exports — regional dependence",
                                "description": (
                                    "Where Singapore's industrial-chemical exports go — covering "
                                    "SITC 5 (chemicals and related products) less SITC 51 (organic "
                                    "chemicals) less SITC 54 (medicinal and pharmaceutical products), "
                                    "i.e. the basic industrial-chemicals subset most exposed to upstream "
                                    "cost pressure from Middle East energy supply disruption. Annual "
                                    "shares on the left; monthly levels on the right."
                                ),
                                "columns": 1,
                                "single_legend": True,   # one legend per card across left+right charts
                                "nodes": [
                                    {
                                        "label": "Regional destinations of Singapore industrial-chemical exports",
                                        "description": "Stacked bars by regional partner. Left: annual % shares (2023–2025); bar height caps at the regional aggregate share. Right: monthly levels in SGD thousands; 'Others' = non-regional destinations (mainly US/EU).",
                                        "subcharts": [
                                            {
                                                "subtitle":     "Annual shares (2023–2025)",
                                                "chart_type":   "bar",
                                                "x_axis_type":  "category",
                                                "stacked":      True,
                                                "series": [f"sg_chem_export_share_{c}" for c in ("cn","in","id","jp","my","ph","kr","tw","th","vn")],
                                            },
                                            {
                                                "subtitle":     "Monthly levels",
                                                "chart_type":   "bar",
                                                "x_axis_type":  "category",
                                                "stacked":      True,
                                                "series": [f"singstat_chem_export_monthly_{c}" for c in ("cn","in","id","jp","my","ph","kr","tw","th","vn")]
                                                          + ["sg_chem_export_monthly_others"],
                                            },
                                        ],
                                    },
                                ],
                            },
                        ],
                    },
                    {
                        "slug": "shipping",
                        "label": "Shipping",
                        "hide_date_range": True,   # nowcast charts have their own time-range
                        "subsections": [
                            # Funnel structure: upstream chokepoint → SG aggregate → per-VT drill-down.
                            # Card 1: Malacca Strait — the upstream pipeline. Disruption shows up
                            # here first, before it filters into SG port calls.
                            {
                                "type": "chart_grid",
                                "title": "Malacca Strait — total weekly transits",
                                "description": (
                                    "Singapore sits at the eastern end of the Malacca Strait — most "
                                    "of SG's seaborne trade passes through it. Tracking Malacca "
                                    "transits gives an early warning signal for upstream disruption "
                                    "before it shows up in SG port calls."
                                ),
                                "columns": 1,
                                "zoom_button": True,
                                "nodes": [
                                    {
                                        "label": "Malacca Strait weekly transits",
                                        "description": "Weekly vessel transits through the Malacca Strait, all vessel types combined. Solid blue is actual; dashed amber is the counterfactual estimate of what transits would have been absent the war.",
                                        "series": [
                                            "nowcast_malacca_total_actual",
                                            "nowcast_malacca_total_cf",
                                        ],
                                    },
                                ],
                            },
                            # Card 2: total SG port calls overview — country-level aggregate
                            {
                                "type": "chart_grid",
                                "title": "Singapore port calls — overview",
                                "description": (
                                    "Singapore's total weekly port calls — actual versus the "
                                    "counterfactual estimate of what calls would have been "
                                    "absent the war."
                                ),
                                "columns": 1,
                                "zoom_button": True,
                                "nodes": [
                                    {
                                        "label": "Total port calls",
                                        "description": "Weekly count of all vessel types arriving at Singapore (imports plus exports). Solid blue is actual; dashed amber is the counterfactual primary estimate.",
                                        "series": [
                                            "nowcast_sg_total_calls_actual",
                                            "nowcast_sg_total_calls_cf",
                                        ],
                                    },
                                ],
                            },
                            # Cards 3-4: per-vessel-type drill-down (tanker + container)
                            {
                                "type": "chart_grid",
                                "title": "Singapore shipping activity — by vessel type",
                                "description": (
                                    "Vessel-type drill-down for the two categories most directly "
                                    "exposed to Iran-related disruption: tankers (energy trade) and "
                                    "containers (general goods). Each card shows three weekly "
                                    "metrics — port calls (vessel count), import tonnage (cargo "
                                    "unloaded), and export tonnage (cargo loaded) — so the war "
                                    "effect can be traced to vessel traffic, inbound cargo, or "
                                    "outbound cargo separately."
                                ),
                                "columns": 1,
                                "zoom_button": True,
                                "nodes": [
                                    {
                                        "label": "Tankers",
                                        "description": "Vessels carrying crude, refined products, LNG, and chemicals — the category most directly exposed to Iran/Hormuz disruption. Sub-charts split out vessel calls and inbound/outbound cargo tonnage.",
                                        "subcharts": [
                                            {"subtitle": "Port calls (count)",
                                             "chart_type": "line", "x_axis_type": "time", "stacked": False,
                                             "series": ["nowcast_sg_tanker_calls_actual", "nowcast_sg_tanker_calls_cf"]},
                                            {"subtitle": "Import tonnage (cargo unloaded)",
                                             "chart_type": "line", "x_axis_type": "time", "stacked": False,
                                             "series": ["nowcast_sg_tanker_imp_tonnage_actual", "nowcast_sg_tanker_imp_tonnage_cf"]},
                                            {"subtitle": "Export tonnage (cargo loaded)",
                                             "chart_type": "line", "x_axis_type": "time", "stacked": False,
                                             "series": ["nowcast_sg_tanker_exp_tonnage_actual", "nowcast_sg_tanker_exp_tonnage_cf"]},
                                        ],
                                    },
                                    {
                                        "label": "Containers",
                                        "description": "General-merchandise vessel traffic — captures broader trade-flow impact from energy-price knock-on effects and supply-chain rerouting. Sub-charts split out vessel calls and inbound/outbound cargo tonnage.",
                                        "subcharts": [
                                            {"subtitle": "Port calls (count)",
                                             "chart_type": "line", "x_axis_type": "time", "stacked": False,
                                             "series": ["nowcast_sg_container_calls_actual", "nowcast_sg_container_calls_cf"]},
                                            {"subtitle": "Import tonnage (cargo unloaded)",
                                             "chart_type": "line", "x_axis_type": "time", "stacked": False,
                                             "series": ["nowcast_sg_container_imp_tonnage_actual", "nowcast_sg_container_imp_tonnage_cf"]},
                                            {"subtitle": "Export tonnage (cargo loaded)",
                                             "chart_type": "line", "x_axis_type": "time", "stacked": False,
                                             "series": ["nowcast_sg_container_exp_tonnage_actual", "nowcast_sg_container_exp_tonnage_cf"]},
                                        ],
                                    },
                                ],
                            },
                        ],
                    },
                    {
                        "slug": "financial_markets",
                        "label": "Financial markets",
                        "subsections": [
                            # Section ordering matches the Regional Financial Markets
                            # tab: Foreign exchange → Interest rates → Equity markets.
                            # ── Section 1: Foreign exchange ──
                            {
                                "type": "chart_grid",
                                "title": "Foreign exchange",
                                "description": (
                                    "USD/SGD spot, forward curve, effective exchange rates, "
                                    "and option-implied volatility. The MAS NEER is the "
                                    "policy band's reference; REER strips out domestic vs. "
                                    "trade-partner inflation to give a real competitiveness "
                                    "view."
                                ),
                                "columns": 2,
                                "nodes": [
                                    {
                                        "label": "USD/SGD — spot vs 1M / 3M forwards",
                                        "description": "Daily SGD/USD spot, 1-month and 3-month forwards. Forward premium widens when SGD rates drop relative to USD (FX-implied rate differential).",
                                        "series": [
                                            "gsheets_us_dollar_singapore_dollar",
                                            "gsheets_singapore_dollar_1_mo",
                                            "gsheets_singapore_dollar_3_mo",
                                        ],
                                    },
                                    {
                                        "label": "Effective exchange rates — NEER vs REER",
                                        "description": "Daily Singapore Nominal Effective Exchange Rate (NEER) and Real Effective Exchange Rate (REER), trade-weighted indices vs MAS basket. NEER is the policy band reference; REER deflates by relative inflation.",
                                        "series": [
                                            "gsheets_nominal_effec_rt",
                                            "gsheets_singapore_real_effective_excha",
                                        ],
                                    },
                                    {
                                        "label": "USD/SGD implied vol — 1M vs 3M",
                                        "description": "Daily option-implied volatility on USD/SGD pair, 1-month and 3-month tenors. Spikes signal expected currency turbulence; also a forward-looking proxy for risk-off sentiment.",
                                        "series": [
                                            "gsheets_usd_sgd_opt_vol_1m",
                                            "gsheets_usd_sgd_opt_vol_3m",
                                        ],
                                    },
                                    {
                                        "label": "Forex monthly turnover",
                                        "description": "Monthly Singapore FX market turnover (SGD millions) — MAS Survey of Forex Market Activity. Includes spot, forwards, swaps, options, and other derivatives across all currency pairs traded out of Singapore.",
                                        "series": ["financial_forex_turnover"],
                                    },
                                ],
                            },
                            # ── Section 2: Interest rates ──
                            {
                                "type": "chart_grid",
                                "title": "Interest rates",
                                "description": (
                                    "Singapore short-end and long-end interest rates. "
                                    "Iran/Hormuz energy shocks tend to push longer yields "
                                    "higher (term-premium repricing on inflation risk) and "
                                    "money-market rates higher (USD funding stress passing "
                                    "through to SGD via FX-implied rates)."
                                ),
                                "columns": 2,
                                "nodes": [
                                    {
                                        "label": "SGS yield curve — 2Y vs 10Y",
                                        "description": "Daily yields on Singapore Government Securities, % per annum. The 2Y–10Y spread captures the slope of the curve.",
                                        "series": ["financial_yield_2y", "financial_yield_10y"],
                                    },
                                    {
                                        "label": "BVAL yield curve — 2Y vs 10Y",
                                        "description": "Bloomberg Valuation (BVAL) SGS yields, daily. Independent market-implied curve — small basis vs the MAS reference yields above.",
                                        "series": [
                                            "gsheets_sgd_singapore_govt_bval_2y",
                                            "gsheets_sgd_singapore_govt_bval_10y",
                                        ],
                                    },
                                    {
                                        "label": "SORA 3M compounded",
                                        "description": "Singapore Overnight Rate Average compounded over 3 months — the post-2024 reference rate for SGD-denominated lending.",
                                        "series": ["financial_sora_3m"],
                                    },
                                    {
                                        "label": "Domestic interbank — overnight",
                                        "description": "Singapore domestic interbank average overnight rate, daily. The shortest end of the SGD money-market curve.",
                                        "series": ["gsheets_s_pore_domestic_ib_avg_o_n"],
                                    },
                                ],
                            },
                            # ── Section 3: Equity markets ──
                            {
                                "type": "chart_grid",
                                "title": "Equity markets",
                                "description": (
                                    "Singapore equity market gauges. STI is the headline 30-stock "
                                    "blue-chip index; SGX turnover captures volume. Risk-off "
                                    "episodes typically show STI dropping with elevated turnover."
                                ),
                                "columns": 2,
                                "nodes": [
                                    {
                                        "label": "Straits Times Index (STI)",
                                        "description": "Daily Straits Times Index — 30 largest SGX-listed companies by market cap. Headline benchmark for SG equity performance.",
                                        "series": ["gsheets_straits_times_index_sti"],
                                    },
                                    {
                                        "label": "SGX daily turnover",
                                        "description": "Daily SGX equity turnover, millions of shares. Spikes typically coincide with risk-off episodes or earnings/index-rebalancing days.",
                                        "series": ["financial_sgx_turnover"],
                                    },
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
            # LLM-generated tight summary + key_findings bullets per question.
            {"type": "page_summary"},
            {
                "type": "tab_group",
                "tabs": [
                    {
                        "slug": "prices",
                        "label": "Prices",
                        "subsections": [
                            {
                                "type": "chart_grid",
                                "title": "Inflation — Annual",
                                "description": (
                                    "Year-on-year inflation across 10 Asian economies "
                                    "(China, India, Indonesia, Japan, Malaysia, Philippines, "
                                    "South Korea, Taiwan, Thailand, Vietnam). Each chart shows "
                                    "headline CPI and core CPI side-by-side: headline captures "
                                    "the broadest pass-through of the Iran/Hormuz energy shock; "
                                    "core strips out food and energy to expose second-round effects."
                                ),
                                "nodes": [
                                    {"label": "China",       "description": "Headline and core CPI for China — year-on-year, % change.",          "series": ["regional_cpi_headline_cn", "regional_cpi_core_cn"]},
                                    {"label": "India",       "description": "Headline and core CPI for India — year-on-year, % change.",          "series": ["regional_cpi_headline_in", "regional_cpi_core_in"]},
                                    {"label": "Indonesia",   "description": "Headline and core CPI for Indonesia — year-on-year, % change.",      "series": ["regional_cpi_headline_id", "regional_cpi_core_id"]},
                                    {"label": "Japan",       "description": "Headline and core CPI for Japan — year-on-year, % change.",          "series": ["regional_cpi_headline_jp", "regional_cpi_core_jp"]},
                                    {"label": "Malaysia",    "description": "Headline and core CPI for Malaysia — year-on-year, % change.",       "series": ["regional_cpi_headline_my", "regional_cpi_core_my"]},
                                    {"label": "Philippines", "description": "Headline and core CPI for the Philippines — year-on-year, % change.","series": ["regional_cpi_headline_ph", "regional_cpi_core_ph"]},
                                    {"label": "South Korea", "description": "Headline and core CPI for South Korea — year-on-year, % change.",    "series": ["regional_cpi_headline_kr", "regional_cpi_core_kr"]},
                                    {"label": "Taiwan",      "description": "Headline and core CPI for Taiwan — year-on-year, % change.",         "series": ["regional_cpi_headline_tw", "regional_cpi_core_tw"]},
                                    {"label": "Thailand",    "description": "Headline and core CPI for Thailand — year-on-year, % change.",       "series": ["regional_cpi_headline_th", "regional_cpi_core_th"]},
                                    {"label": "Vietnam",     "description": "Headline and core CPI for Vietnam — year-on-year, % change.",        "series": ["regional_cpi_headline_vn", "regional_cpi_core_vn"]},
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
                                "title": "Industrial Production — Annual",
                                "description": (
                                    "Year-on-year change in industrial / manufacturing production "
                                    "across 10 Asian economies — real-side activity gauges that "
                                    "show where higher energy and input costs are biting into "
                                    "manufacturing output. All series are % year-on-year for "
                                    "direct cross-country comparison."
                                ),
                                "nodes": [
                                    {"label": "China",       "description": "Headline industrial activity for China — official Value Added of Industry, year-on-year.",                       "series": ["regional_ipi_cn"]},
                                    {"label": "India",       "description": "India's industrial production index, year-on-year — covers mining, manufacturing, and electricity output.",      "series": ["regional_ipi_in"]},
                                    {"label": "Indonesia",   "description": "Indonesia's industrial production index, year-on-year. Publishes with a longer lag than peers, so recent months may be sparse.", "series": ["regional_ipi_id"]},
                                    {"label": "Japan",       "description": "Japan's mining and manufacturing industrial production index, year-on-year.",                                     "series": ["regional_ipi_jp"]},
                                    {"label": "Malaysia",    "description": "Malaysia's industrial production index, year-on-year — covers mining, manufacturing, and electricity.",          "series": ["regional_ipi_my"]},
                                    {"label": "Philippines", "description": "Philippines manufacturing output, year-on-year — volume-based industrial production index.",                      "series": ["regional_ipi_ph"]},
                                    {"label": "South Korea", "description": "South Korea total manufacturing production, year-on-year (seasonally adjusted, OECD-harmonised).",                "series": ["regional_ipi_kr"]},
                                    {"label": "Taiwan",      "description": "Taiwan's industrial production index, year-on-year.",                                                              "series": ["regional_ipi_tw"]},
                                    {"label": "Thailand",    "description": "Thailand's industrial production index, year-on-year.",                                                           "series": ["regional_ipi_th"]},
                                    {"label": "Vietnam",     "description": "Vietnam's industrial production index, year-on-year.",                                                            "series": ["regional_ipi_vn"]},
                                ],
                            },
                        ],
                    },
                    {
                        "slug": "trade",
                        "label": "Trade Exposure",
                        "hide_date_range": True,    # bar charts; zoom selector irrelevant
                        "subsections": [
                            # ── Single section, two product views (selector switches) ──
                            # Each view shows the same card structure (cross-country
                            # comparison + 10 per-country monthly cards) but for a
                            # different product.
                            #
                            # Source mix (same for both views):
                            #  - Annual shares: `trade_comtrade_dep` (Comtrade) — SG's
                            #    share of each reporter's product imports.
                            #  - Monthly levels: `trade_singstat` (SingStat sheet) — SG's
                            #    reported exports to each country, aliased by
                            #    `compute_regional_chem_levels` / `compute_regional_fuel_levels`.
                            #  Mirror-trade gap (~5-10%) between SingStat-reported and
                            #  Comtrade-reported is acceptable for a directional story.
                            {
                                "type": "view_selector",
                                "title": "Regional dependence on Singapore — by product",
                                "description": (
                                    "Use the dropdown to switch between two product views. "
                                    "Industrial chemicals capture Singapore's value-add chemical "
                                    "exports; refined petroleum captures Singapore's role as the "
                                    "regional refining hub for Middle East crude. Indonesia, "
                                    "Malaysia, and Thailand are most exposed in both, but the "
                                    "magnitude differs sharply — single-digit shares for chemicals "
                                    "versus 30–50% for refined petroleum."
                                ),
                                "views": [
                                    # ──────── View 1: Refined petroleum (default — leads the selector) ────────
                                    # SITC 334 is the headline regional dependence story —
                                    # SG as the regional refining hub for ME-imported crude
                                    # produces sharper rankings (ID 53%, MY 34%, others 6-10%)
                                    # than chemicals (~5-12% range).
                                    {
                                        "label": "Refined petroleum",
                                        "key": "fuel",
                                        "default": True,
                                        "subsections": [
                                            {
                                                "type": "country_share_comparison",
                                                "slug": "regional_fuel_share_comparison",
                                                "title": "Refined petroleum imports from Singapore — annual SG shares by regional country",
                                                "description": (
                                                    "How dependent each regional economy is on Singapore for "
                                                    "refined-petroleum imports — SITC 334 (gasoline, diesel, jet "
                                                    "fuel, naphtha, fuel oil). Indirect channel through which "
                                                    "Middle East crude disruption reaches the region via Singapore's "
                                                    "refining hub. Ordered by 2024 share."
                                                ),
                                                "categories": [
                                                    ("Indonesia",    "id"),
                                                    ("Malaysia",     "my"),
                                                    ("Thailand",     "th"),
                                                    ("Philippines",  "ph"),
                                                    ("Taiwan",       "tw"),
                                                    ("China",        "cn"),
                                                    ("India",        "in"),
                                                    ("South Korea",  "kr"),
                                                    ("Japan",        "jp"),
                                                    ("Vietnam",      "vn"),
                                                ],
                                                "year_series": [
                                                    ("2023", "2023-12-31"),
                                                    ("2024", "2024-12-31"),
                                                ],
                                                "series_id_template": "regional_fuel_share_from_sg_{key}",
                                                "unit": "% share",
                                            },
                                            {
                                                "type": "chart_grid",
                                                "title": "Refined petroleum imports from Singapore — monthly levels by regional country",
                                                "description": (
                                                    "Monthly absolute imports of refined petroleum (SITC 334) from "
                                                    "Singapore in SGD thousands, with the 2023–24 monthly average "
                                                    "as a dashed reference line. Cards ordered by 2024 Singapore "
                                                    "share, descending."
                                                ),
                                                "chart_type":  "bar",
                                                "x_axis_type": "category",
                                                "columns":     2,
                                                "hide_chart_title": True,
                                                "hide_legend":      True,
                                                "benchmark_label":  "2023-24 avg",
                                                "nodes": [
                                                    {"label": label, "description": "",
                                                     "series": [f"regional_fuel_imports_from_sg_{iso2}"]}
                                                    for iso2, label in [
                                                        ("id", "Indonesia"), ("my", "Malaysia"),
                                                        ("th", "Thailand"), ("ph", "Philippines"),
                                                        ("tw", "Taiwan"), ("cn", "China"),
                                                        ("in", "India"), ("kr", "South Korea"),
                                                        ("jp", "Japan"), ("vn", "Vietnam"),
                                                    ]
                                                ],
                                            },
                                        ],
                                    },
                                    # ──────── View 2: Industrial chemicals ────────
                                    {
                                        "label": "Industrial chemicals",
                                        "key": "chem",
                                        "subsections": [
                                            {
                                                "type": "country_share_comparison",
                                                "slug": "regional_chem_share_comparison",
                                                "title": "Industrial chemical imports from Singapore — annual SG shares by regional country",
                                                "description": (
                                                    "How dependent each regional economy is on Singapore for "
                                                    "industrial-chemical imports — SITC 5 less SITC 51 (organics) "
                                                    "less SITC 54 (pharmaceuticals), the chemicals subset most "
                                                    "exposed to Middle East upstream cost pressure. Ordered by 2024 "
                                                    "share."
                                                ),
                                                "categories": [
                                                    ("Malaysia",     "my"),
                                                    ("Indonesia",    "id"),
                                                    ("Philippines",  "ph"),
                                                    ("Thailand",     "th"),
                                                    ("China",        "cn"),
                                                    ("India",        "in"),
                                                    ("South Korea",  "kr"),
                                                    ("Japan",        "jp"),
                                                    ("Taiwan",       "tw"),
                                                    ("Vietnam",      "vn"),
                                                ],
                                                "year_series": [
                                                    ("2023", "2023-12-31"),
                                                    ("2024", "2024-12-31"),
                                                ],
                                                "series_id_template": "regional_chem_share_from_sg_{key}",
                                                "unit": "% share",
                                            },
                                            {
                                                "type": "chart_grid",
                                                "title": "Industrial chemical imports from Singapore — monthly levels by regional country",
                                                "description": (
                                                    "Monthly absolute imports of industrial chemicals (SITC 5 less "
                                                    "51 less 54) from Singapore in SGD thousands, with the 2023–24 "
                                                    "monthly average as a dashed reference line. Cards ordered by "
                                                    "2024 Singapore share, descending."
                                                ),
                                                "chart_type":  "bar",
                                                "x_axis_type": "category",
                                                "columns":     2,
                                                "hide_chart_title": True,
                                                "hide_legend":      True,
                                                "benchmark_label":  "2023-24 avg",
                                                "nodes": [
                                                    {"label": label, "description": "",
                                                     "series": [f"regional_chem_imports_from_sg_{iso2}"]}
                                                    for iso2, label in [
                                                        ("my", "Malaysia"), ("id", "Indonesia"),
                                                        ("ph", "Philippines"), ("th", "Thailand"),
                                                        ("cn", "China"), ("in", "India"),
                                                        ("kr", "South Korea"), ("jp", "Japan"),
                                                        ("tw", "Taiwan"), ("vn", "Vietnam"),
                                                    ]
                                                ],
                                            },
                                        ],
                                    },
                                ],
                            },
                        ],
                    },
                    {
                        "slug": "shipping",
                        "label": "Shipping",
                        "hide_date_range": True,   # nowcast charts have their own time range
                        "subsections": [
                            # One country-selector widget driving N "country panels"
                            # — same card layout as Singapore Shipping (overview ➜ tanker
                            # drill-down ➜ container drill-down), substituted per country.
                            # Series IDs use `{iso2}` as a placeholder that the
                            # country_panels renderer expands per country.
                            {
                                "type": "country_panels",
                                "title": "Regional shipping nowcast",
                                "description": (
                                    "Same shipping nowcast cards as the Singapore tab, "
                                    "shown one regional country at a time. Pick a country "
                                    "from the selector to switch the view. Source: IMF "
                                    "PortWatch satellite data, processed by the MAS "
                                    "shipping nowcast pipeline."
                                ),
                                "countries": [
                                    # (iso2, display_label) — order = dropdown order.
                                    ("cn", "China"),
                                    ("in", "India"),
                                    ("id", "Indonesia"),
                                    ("jp", "Japan"),
                                    ("kr", "South Korea"),
                                    ("my", "Malaysia"),
                                    ("ph", "Philippines"),
                                    ("th", "Thailand"),
                                    ("vn", "Vietnam"),
                                ],
                                "default_country": "cn",
                                # subsection_template — same shape as the Singapore Shipping
                                # `subsections` list, just with `{iso2}` placeholders that
                                # the renderer expands to e.g. `cn`, `my`, etc.
                                "subsection_template": [
                                    # Card 1: country total port calls overview
                                    {
                                        "type": "chart_grid",
                                        "title": "{country} port calls — overview",
                                        "description": (
                                            "{country}'s total weekly port calls — actual vs "
                                            "the counterfactual estimate of what calls would "
                                            "have been absent the war."
                                        ),
                                        "columns": 1,
                                        "zoom_button": True,
                                        "nodes": [
                                            {
                                                "label": "Total port calls (all vessel types, imports + exports)",
                                                "description": "Weekly aggregate of all vessel types arriving at this country's ports. Solid blue is actual; dashed amber is the counterfactual primary estimate.",
                                                "series": [
                                                    "nowcast_{iso2}_total_calls_actual",
                                                    "nowcast_{iso2}_total_calls_cf",
                                                ],
                                            },
                                        ],
                                    },
                                    # Cards 2-3: per-vessel-type drill-down (tanker + container)
                                    {
                                        "type": "chart_grid",
                                        "title": "{country} shipping activity — by vessel type",
                                        "description": (
                                            "Vessel-type drill-down for the two categories "
                                            "most directly exposed to Iran-related disruption: "
                                            "tankers (energy trade) and containers (general "
                                            "goods). Each card shows three weekly metrics — "
                                            "port calls (vessel count), import tonnage (cargo "
                                            "unloaded), and export tonnage (cargo loaded)."
                                        ),
                                        "columns": 1,
                                        "zoom_button": True,
                                        "nodes": [
                                            {
                                                "label": "Tanker",
                                                "description": "Tanker activity — vessels carrying crude oil, refined products, LNG, and chemicals. Most directly exposed to Iran/Hormuz disruption.",
                                                "subcharts": [
                                                    {"subtitle": "Port calls (count)",
                                                     "chart_type": "line", "x_axis_type": "time", "stacked": False,
                                                     "series": ["nowcast_{iso2}_tanker_calls_actual", "nowcast_{iso2}_tanker_calls_cf"]},
                                                    {"subtitle": "Import tonnage (cargo unloaded)",
                                                     "chart_type": "line", "x_axis_type": "time", "stacked": False,
                                                     "series": ["nowcast_{iso2}_tanker_imp_tonnage_actual", "nowcast_{iso2}_tanker_imp_tonnage_cf"]},
                                                    {"subtitle": "Export tonnage (cargo loaded)",
                                                     "chart_type": "line", "x_axis_type": "time", "stacked": False,
                                                     "series": ["nowcast_{iso2}_tanker_exp_tonnage_actual", "nowcast_{iso2}_tanker_exp_tonnage_cf"]},
                                                ],
                                            },
                                            {
                                                "label": "Container",
                                                "description": "Container activity — general merchandise. Reflects broader trade impact (knock-on effect from energy price shocks, supply-chain re-routing).",
                                                "subcharts": [
                                                    {"subtitle": "Port calls (count)",
                                                     "chart_type": "line", "x_axis_type": "time", "stacked": False,
                                                     "series": ["nowcast_{iso2}_container_calls_actual", "nowcast_{iso2}_container_calls_cf"]},
                                                    {"subtitle": "Import tonnage (cargo unloaded)",
                                                     "chart_type": "line", "x_axis_type": "time", "stacked": False,
                                                     "series": ["nowcast_{iso2}_container_imp_tonnage_actual", "nowcast_{iso2}_container_imp_tonnage_cf"]},
                                                    {"subtitle": "Export tonnage (cargo loaded)",
                                                     "chart_type": "line", "x_axis_type": "time", "stacked": False,
                                                     "series": ["nowcast_{iso2}_container_exp_tonnage_actual", "nowcast_{iso2}_container_exp_tonnage_cf"]},
                                                ],
                                            },
                                        ],
                                    },
                                ],
                            },
                        ],
                    },
                    {
                        "slug": "financial_markets",
                        "label": "Financial markets",
                        "subsections": [
                            # ── Section 1: Exchange rates (single full-width chart) ──
                            {
                                "type": "chart_grid",
                                "title": "Exchange rates",
                                "description": (
                                    "Daily Asian currency rates against USD, rebased to 100 at "
                                    "2026-01-01 so currencies with very different magnitudes can "
                                    "share an axis. Higher = local currency weaker vs USD. Source: "
                                    "yfinance."
                                ),
                                "columns": 1,
                                "series_groups": [
                                    ("Currency strength vs USD (indexed, 2026-01-01 = 100)",
                                     ["fx_indexed_idr", "fx_indexed_myr", "fx_indexed_php",
                                      "fx_indexed_thb", "fx_indexed_vnd", "fx_indexed_jpy",
                                      "fx_indexed_cny"]),
                                ],
                            },
                            # ── Section 2: 10Y sovereign bond yields (single full-width chart) ──
                            # forward_fill carries the most recent quote forward for
                            # sparse series (notably PH 10Y, which is auction-only at
                            # ~1-2 quotes/month) so the Chart.js tooltip in 'index' mode
                            # shows every series at every hover position.
                            {
                                "type": "chart_grid",
                                "title": "Bond yields",
                                "description": (
                                    "Daily 10-year government bond yields, % per annum. US from "
                                    "yfinance (^TNX); ASEAN-4 + Vietnam from CEIC."
                                ),
                                "columns": 1,
                                "forward_fill": True,
                                "series_groups": [
                                    ("Sovereign 10-year bond yields (% per annum)",
                                     ["US_10Y", "ID_10Y", "MY_10Y", "PH_10Y", "TH_10Y", "VN_10Y"]),
                                ],
                            },
                            # ── Section 3: Commodity prices (multi-card grid) ──
                            # Each commodity has its own card with a brief explainer.
                            # Card <h3> already labels the commodity; suppress the
                            # Chart.js title and legend (single-series → both redundant).
                            # Brent crude oil is omitted here — already on Global Shocks
                            # tab (no point duplicating).
                            {
                                "type": "chart_grid",
                                "title": "Commodity prices",
                                "description": (
                                    "Key commodity benchmarks relevant to Asian trade and energy "
                                    "exposure. yfinance for COMEX/ICE-listed contracts (Gold, "
                                    "Copper, LME Aluminum); investing.com for niche regional "
                                    "benchmarks (LME Nickel, FCPO MYR, JKM LNG, Newcastle coal, "
                                    "rubber TSR20)."
                                ),
                                # Override the regional.financial_markets default — these
                                # commodity cards are price-level / supply-cost indicators
                                # for the LLM's energy_supply question, not for the
                                # financial-tightening question. Gold is the one exception
                                # (per-card override below).
                                "relevant_to":      ["energy_supply"],
                                "columns":          2,
                                "hide_chart_title": True,
                                "hide_legend":      True,
                                "nodes": [
                                    {"label": "Gold",
                                     "description": "COMEX gold futures front-month (USD/oz). Global safe-haven benchmark; Iran/Hormuz tensions typically push gold higher.",
                                     "series": ["GOLD"],
                                     # Per-card override: gold is a financial-stress signal
                                     # (safe-haven flow), not a supply-cost signal like
                                     # the other commodities in this section.
                                     "relevant_to": ["financial_markets"]},
                                    {"label": "Copper",
                                     "description": "COMEX copper futures (USD/lb). Leading indicator of global industrial demand and a proxy for China growth.",
                                     "series": ["COPPER"]},
                                    {"label": "Aluminum",
                                     "description": "LME aluminum 3-month forward (USD/tonne). Major industrial metal, energy-intensive to produce so sensitive to power costs.",
                                     "series": ["ALUMINUM"]},
                                    {"label": "Nickel",
                                     "description": "LME nickel (USD/tonne). Used in stainless steel and EV batteries; Indonesia is the largest producer and SE Asia a major refiner.",
                                     "series": ["NICKEL"]},
                                    {"label": "JKM LNG",
                                     "description": "Japan/Korea Marker (USD/MMBtu). The Asian spot LNG benchmark assessed daily by Platts. Spikes when Hormuz transit risk rises — Qatari LNG accounts for ~20% of global supply.",
                                     "series": ["JKM_LNG"]},
                                    {"label": "Rubber TSR20",
                                     "description": "Bangkok STR 20 (≡ TSR 20), 2nd-month FOB price, converted to USc/kg via daily FX. Asian natural rubber benchmark — Thailand leads regional production, with Indonesia and Vietnam close behind.",
                                     "series": ["RUBBER_TSR20"]},
                                    # Coal and CPO at the bottom — both still on day-by-day
                                    # investing.com accumulation (~30 days, no pre-war
                                    # context). The new "Data starts ..." stale label
                                    # surfaces this on each card.
                                    {"label": "Newcastle coal",
                                     "description": "Newcastle FOB Australia thermal coal (USD/tonne). The seaborne Asian thermal coal benchmark; a substitute fuel that often moves with LNG.",
                                     "series": ["COAL_NEWC"]},
                                    {"label": "Crude palm oil",
                                     "description": "FCPO front-month on Bursa Malaysia (MYR/tonne). The global palm oil benchmark. Important for Indonesia and Malaysia (top exporters).",
                                     "series": ["CPO"]},
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
