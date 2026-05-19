"""
Dependency node configuration for the dashboard.

The flowchart traces how an Iran-war energy supply disruption transmits
through to Singapore's economy in four tiers:

  Tier 1  Energy Prices         — "What prices spiked?"
  Tier 2  Refined Products      — "What products got more expensive?"
  Tier 3  Industrial Inputs     — "What industrial inputs are affected?"
  Tier 4  SG Economic Activity  — "Where do we see it in Singapore's economy?"

Parent → child edges encode the specific transmission channel
(e.g. marine_fuel → water_transport means "marine fuel cost → shipping activity").

Preferred mapping approach:
- Put CEIC series ids directly in `series_ids`
- Put exact Google Sheets row-2 names in `google_sheet_series`
"""

# 2026-04-30: enable PEP 604 (X | Y) annotation syntax under Python 3.9.
# `from __future__ import annotations` defers all annotation evaluation to
# string form so `list[str] | None` is valid at runtime even on 3.9. (CEIC
# client itself still requires 3.10+; this just unblocks our own modules.)
from __future__ import annotations


def node(
    *,
    label: str,
    description: str,
    children: list[str] | None = None,
    series_ids: list[str] | None = None,
    google_sheet_series: list[str] | None = None,
    sheet_keywords: list[str] | None = None,
) -> dict:
    return {
        "label": label,
        "description": description,
        "children": children or [],
        "series_ids": series_ids or [],
        "google_sheet_series": google_sheet_series or [],
        "sheet_keywords": sheet_keywords or [],
    }


DEPENDENCY_NODES = {
    # ==================================================================
    # TIER 1 — Upstream Energy Prices ("What prices spiked?")
    # ==================================================================
    "crude_oil": node(
        label="Crude Oil",
        description="Global crude benchmarks.",
        children=[
            "marine_fuel",
            "jet_fuel",
            "diesel_petrol",
            "lpg",
            "naphtha",
        ],
        series_ids=[
            "global_crude_oil",
            "global_crude_oil_wti",
        ],
        google_sheet_series=[],
        sheet_keywords=["crude"],
    ),
    # Dated Brent vs front-month ICE Brent futures spread — gauge of
    # prompt physical-market tightness. Spread is already pre-computed
    # in the "Upstream Commodities" tab of the Google Sheet.
    "brent_dated_front_spread": node(
        label="Dated Brent spread",
        description=(
            "Premium of Dated Brent (physical North Sea benchmark) over the "
            "front-month ICE Brent futures contract."
        ),
        google_sheet_series=[
            "Spread between Dated Brent and front-month ICE Brent futures contract",
        ],
        sheet_keywords=["spread between dated brent"],
    ),
    # Urals crude vs major benchmarks + price caps — demand signal for
    # Russian oil. Trading above the cap signals access to non-Western
    # shipping/insurance; a narrow discount to Brent/Dubai signals
    # resilient demand despite sanctions.
    "urals_vs_benchmarks": node(
        label="Urals crude vs benchmarks",
        description=(
            "Urals crude alongside Dated Brent and Dubai benchmarks, with the "
            "G7/EU and US price caps shown as dashed reference lines."
        ),
        google_sheet_series=[
            "Crude Oil Dated Brent FOB NWE",
            "GX Crude Oil Dubai FOB Partial Cargoes Month",
            "Urals Crude Oil",
            "US Price Cap",
            "EU-UK Price Cap",
        ],
        sheet_keywords=["urals", "price cap"],
    ),
    "natural_gas": node(
        label="Natural Gas",
        description="Global gas benchmarks.",
        children=[
            "fertilisers",
            "gas_electricity",
            "lpg",
        ],
        series_ids=[
            "global_us_natural_gas",
            "global_germany_natural_gas",
        ],
        google_sheet_series=[],
        sheet_keywords=["gas", "lng", "natural gas"],
    ),

    # ==================================================================
    # TIER 2 — Refined Products ("What products got more expensive?")
    # ==================================================================
    "marine_fuel": node(
        label="Marine Fuel",
        description="Bunker fuel prices (VLSFO, 380cst).",
        children=[
            "water_transport",
            "wholesale",
        ],
        google_sheet_series=[
            "ClearLynx VLSFO Bunker Fuel Spot Price/Singapore",
            "Asia Fuel Oil 380cst FOB Singapore Cargo Spot",
        ],
        sheet_keywords=["marine fuel", "bunker", "fuel oil"],
    ),
    "jet_fuel": node(
        label="Jet Fuel",
        description="Aviation fuel prices.",
        children=[
            "air_transport",
        ],
        google_sheet_series=[
            "Jet Fuel NWE FOB Barges",
            "Jet Fuel Singapore FOB Cargoes vs Crude Oil Dated Brent FOB NWE",
            "PADD I Average Jet Fuel Spot Market Price Prompt",
        ],
        sheet_keywords=["jet fuel", "jet", "aviation fuel"],
    ),
    "diesel_petrol": node(
        label="Diesel / Petrol",
        description="Road fuel prices.",
        children=[
            "land_transport",
        ],
        google_sheet_series=[
            "Gasoline Singapore 92 RON FOB Cargoes",
            "Gasoline Singapore 95 RON FOB Cargoes",
            "RBOB Regular Gasoline NY Buckeye Continuous MKTMID",
        ],
        sheet_keywords=["diesel", "gasoil", "petrol", "gasoline"],
    ),
    "naphtha": node(
        label="Naphtha",
        description="Key petrochemical feedstock.",
        children=[
            "olefins_aromatics",
            "petrochemicals",
            "basic_chemicals",
        ],
        # CEIC monthly Japan/France naphtha removed — they duplicated the Bloomberg
        # daily Japan CIF and NWE Naphtha series at lower frequency and in different
        # units (USD/Barrel and USD/Ton vs USD/metric tonne), creating overlapping
        # lines on different scales. Bloomberg daily is strictly higher quality
        # for war-period analysis.
        series_ids=[],
        google_sheet_series=[
            "Naphtha Japan CIF Cargoes",
            "Naphtha Singapore FOB Cargoes",
            "GX Naphtha NWE CIF Cargoes Prompt",
        ],
        sheet_keywords=["naphtha"],
    ),
    "lpg": node(
        label="LPG",
        description="Propane and butane prices — alternative cracker feedstock and petrochemical input.",
        children=[
            "olefins_aromatics",
        ],
        google_sheet_series=[
            "North American Spot LPGs/NGLs Propane Price/Mont Belvieu LST",
            "North American Spot LPGs/NGLs Normal Butane Price/Mont Belvieu LST",
            "North American Spot LPGs/NGLs Purity Ethane Price/Mont Belvieu non-LST",
            "Bloomberg Arab Gulf LPG Propane Monthly Posted Price",
            "Bloomberg Arab Gulf LPG Butane Monthly Posted Price",
        ],
        sheet_keywords=["lpg", "propane", "butane", "ethane"],
    ),

    # ==================================================================
    # TIER 3 — Industrial Inputs ("What industrial inputs are affected?")
    # ==================================================================
    "olefins_aromatics": node(
        label="Olefins & Aromatics",
        description="Ethylene, propylene, polyethylene — intermediate chemicals.",
        children=[
            "petrochemicals",
            "basic_chemicals",
            "construction",
            "food_beverage",
        ],
        google_sheet_series=[
            "SE Asia Ethylene (Olefins) CFR Spot Price Weekly",
            "US Gulf Ethylene (Olefins) FD Spot Price Weekly",
            "NWE Ethylene CIF Price USD/MT Weekly",
            "NE Asia Ethylene (Olefins) CFR Spot Price Weekly",
            "China Chemicals SunSirs LLDPE Linear Low-Density Polyethylene",
            "China Chemicals SunSirs HDPE High Density Polyethylene",
            "China Chemicals SunSirs PET Polyethylene Terephthalate",
            "SE Asia Film-Grade Polyethylene (HDPE Polymers) CFR Spot Price Weekly",
            "SE Asia Film-Grade Polyethylene (LLDPE Polymers) CFR Spot Price Weekly",
        ],
        sheet_keywords=["olefin", "aromatic", "ethylene", "propylene"],
    ),

    # Presentation-only sub-nodes — split olefins_aromatics into two cleaner
    # charts (ethylene cracker outputs vs downstream polymers) for the Global
    # Shocks page. The combined olefins_aromatics node above is kept intact
    # because naphtha/LPG reference it in the transmission-graph children list.
    "olefins_ethylene": node(
        label="Ethylene",
        description="Regional ethylene spot prices — the primary cracker output and feedstock for downstream polymers.",
        google_sheet_series=[
            "NE Asia Ethylene (Olefins) CFR Spot Price Weekly",
            "SE Asia Ethylene (Olefins) CFR Spot Price Weekly",
            "NWE Ethylene CIF Price USD/MT Weekly",
            "US Gulf Ethylene (Olefins) FD Spot Price Weekly",
        ],
        sheet_keywords=["ethylene"],
    ),
    "olefins_polymers": node(
        label="Polymers",
        description="Polyethylene (HDPE/LLDPE) and PET resin prices in China and Southeast Asia — packaging, pipe, bottle, and fibre inputs.",
        google_sheet_series=[
            "China Chemicals SunSirs HDPE High Density Polyethylene",
            "China Chemicals SunSirs LLDPE Linear Low-Density Polyethylene",
            "China Chemicals SunSirs PET Polyethylene Terephthalate",
            "SE Asia Film-Grade Polyethylene (HDPE Polymers) CFR Spot Price Weekly",
            "SE Asia Film-Grade Polyethylene (LLDPE Polymers) CFR Spot Price Weekly",
        ],
        sheet_keywords=["polyethylene", "polymer", "pet"],
    ),
    "fertilisers": node(
        label="Fertilisers",
        description="Urea and ammonia prices — gas-derived via Haber-Bosch process.",
        children=[
            "food_beverage",
        ],
        series_ids=[
            "ceic_urea_us_gulf",
        ],
        google_sheet_series=[],
        sheet_keywords=["fertiliser", "fertilizer", "urea", "ammonia"],
    ),

    # ==================================================================
    # TIER 4 — SG Economic Activity
    #          "Where do we see it in Singapore's economy?"
    # ==================================================================

    # ── Transport ──
    "water_transport": node(
        label="Water Transport",
        description="Port throughput and cargo volumes.",
        series_ids=[
            "sea_cargo_handled",
            "container_throughput",
        ],
        google_sheet_series=[],
        sheet_keywords=["shipping", "container", "cargo"],
    ),
    "air_transport": node(
        label="Air Transport",
        description="Flight movements, passenger traffic, air freight.",
        series_ids=[
            "air_flight_movements",
            "air_passenger_movements",
            "air_freight_movements",
        ],
        google_sheet_series=[],
        sheet_keywords=["air freight", "aviation", "passenger"],
    ),
    "land_transport": node(
        label="Land Transport",
        description="Road transport activity.",
        children=["sg_cpi"],
        series_ids=[
            "visitor_arrival_land",
            "singstat_petrol_92",
            "singstat_petrol_95",
            "singstat_petrol_98",
            "singstat_diesel",
            "motorist_92",
            "motorist_95",
            "motorist_98",
            "motorist_premium",
            "motorist_diesel",
        ],
        google_sheet_series=[],
        sheet_keywords=["vehicle", "land transport"],
    ),

    # ── Energy & Chemicals ──
    "petroleum": node(
        label="Petroleum Refining",
        description="Refinery output.",
        children=["sg_import_prices", "sg_export_prices"],
        # 2026-04-30: dropped singstat_imports_petroleum/exports_petroleum (the
        # legacy SITC-33-aggregate refining trade card). Same data is now on
        # the Trade Exposure tab broken out by partner at SITC 333/334 levels.
        series_ids=["ipi_petroleum"],
        google_sheet_series=[],
        sheet_keywords=["petroleum", "refinery", "refining"],
    ),
    "petrochemicals": node(
        label="Petrochemicals",
        description="Petrochemical production.",
        children=["sg_producer_prices"],
        series_ids=["ipi_petrochemicals"],
        google_sheet_series=[],
        sheet_keywords=["petrochemical", "polymer"],
    ),
    "basic_chemicals": node(
        label="Specialty and other chemicals",
        description="Industrial production indices for specialty chemicals (paints, coatings, adhesives) and other chemicals (basic intermediates).",
        series_ids=["ipi_specialty_chemicals", "ipi_other_chemicals"],
        google_sheet_series=[],
        sheet_keywords=["chemical", "methanol", "ammonia", "caustic"],
    ),
    "gas_electricity": node(
        label="Electricity tariff (households)",
        description="Low-tension domestic electricity tariff. Almost all of Singapore's power generation runs on imported natural gas, so the tariff tracks LNG and pipeline-gas prices with a lag.",
        children=["sg_cpi", "sg_supply_prices"],
        series_ids=["singstat_electricity_tariff"],
        google_sheet_series=[],
        sheet_keywords=["power", "electricity", "gas"],
    ),

    # ── Wholesale ──
    "wholesale": node(
        label="Wholesale trade",
        description="Foreign Wholesale Trade Index — overall plus the petroleum, chemicals, and ship-chandlers/bunkering subsectors.",
        series_ids=[
            "fwti_overall",
            "fwti_petroleum",
            "fwti_chemical",
            "fwti_bunkering",
        ],
        google_sheet_series=[],
        sheet_keywords=["wholesale", "bunker"],
    ),

    # ── Downstream ──
    "construction_demand": node(
        label="Construction demand",
        description="Construction-sector activity — value of contracts awarded plus physical-volume demand for cement, steel, and granite.",
        series_ids=[
            "singstat_construction_contracts",
            "ceic_constr_demand_cement",
            "ceic_constr_demand_steel",
            "ceic_constr_demand_granite",
        ],
        google_sheet_series=[],
        sheet_keywords=["construction", "cement", "building"],
    ),
    "construction_prices": node(
        label="Construction material prices",
        description="Monthly prices of key construction materials — cement, steel bars, granite, and concreting sand.",
        series_ids=[
            "ceic_constr_price_cement",
            "ceic_constr_price_steel",
            "ceic_constr_price_granite",
            "ceic_constr_price_sand",
        ],
        google_sheet_series=[],
        sheet_keywords=["construction", "cement"],
    ),
    "real_estate": node(
        label="Real estate",
        description="Property-market activity.",
        series_ids=[
            "ceic_property_price_index",
            "ceic_residential_transactions",
        ],
        google_sheet_series=[],
        sheet_keywords=["property", "real estate"],
    ),
    "food_beverage": node(
        label="Food and beverage services",
        description="F&B Services Index — overall sector plus the five segments (restaurants, fast food, caterers, food courts, cafes).",
        children=["sg_cpi"],
        series_ids=[
            "fb_overall",
            "fb_restaurants",
            "fb_fast_food",
            "fb_caterers",
            "fb_food_courts",
            "fb_cafes",
        ],
        google_sheet_series=[],
        sheet_keywords=["food", "beverage", "packaging"],
    ),

    # ==================================================================
    # TIER 5 — SG Consumer Prices
    #          "What does it mean for Singapore's price levels?"
    # ==================================================================
    "sg_cpi": node(
        label="Inflation",
        description="Headline CPI and MAS Core inflation.",
        series_ids=["ceic_cpi_yoy", "ceic_cpi_mom", "ceic_mas_core_inflation", "mas_core_inflation_mom"],
        google_sheet_series=[],
        sheet_keywords=["cpi", "inflation"],
    ),
    "sg_supply_prices": node(
        label="Domestic supply prices",
        description="Prices of goods supplied to the Singapore market — split into oil and non-oil components.",
        series_ids=["ceic_dspi_oil", "ceic_dspi_non_oil"],
        google_sheet_series=[],
        sheet_keywords=["supply price", "dspi"],
    ),
    "sg_producer_prices": node(
        label="Producer prices",
        description="Factory-gate prices for goods manufactured in Singapore (excludes imports), split into oil and non-oil.",
        series_ids=["ceic_mppi_oil", "ceic_mppi_non_oil"],
        google_sheet_series=[],
        sheet_keywords=["producer price", "mppi"],
    ),
    "sg_import_prices": node(
        label="Import prices",
        description="Prices of imports landing in Singapore — split into oil, non-oil, and food components.",
        series_ids=["ceic_ipi_oil", "ceic_ipi_non_oil", "ceic_ipi_food"],
        google_sheet_series=[],
        sheet_keywords=["import price"],
    ),
    "sg_export_prices": node(
        label="Export prices",
        description="Prices Singapore exporters charge overseas buyers — split into oil and non-oil.",
        series_ids=["ceic_epi_oil", "ceic_epi_non_oil"],
        google_sheet_series=[],
        sheet_keywords=["export price"],
    ),

    # ==================================================================
    # REGIONAL — Asia ex-Singapore CPI and Industrial Production
    # ==================================================================
    "regional_cpi_headline": node(
        label="Regional Headline CPI",
        description="Year-on-year headline CPI inflation across 10 Asian economies.",
        series_ids=[
            "regional_cpi_headline_cn",
            "regional_cpi_headline_in",
            "regional_cpi_headline_id",
            "regional_cpi_headline_jp",
            "regional_cpi_headline_my",
            "regional_cpi_headline_ph",
            "regional_cpi_headline_kr",
            "regional_cpi_headline_tw",
            "regional_cpi_headline_th",
            "regional_cpi_headline_vn",
        ],
        google_sheet_series=[],
        sheet_keywords=["cpi", "inflation"],
    ),
    "regional_cpi_core": node(
        label="Regional Core CPI",
        description="Year-on-year core CPI inflation (excluding food and energy) across the same 10 economies.",
        series_ids=[
            "regional_cpi_core_cn",
            "regional_cpi_core_in",
            "regional_cpi_core_id",
            "regional_cpi_core_jp",
            "regional_cpi_core_my",
            "regional_cpi_core_ph",
            "regional_cpi_core_kr",
            "regional_cpi_core_tw",
            "regional_cpi_core_th",
            "regional_cpi_core_vn",
        ],
        google_sheet_series=[],
        sheet_keywords=["core inflation"],
    ),
    "regional_ipi": node(
        label="Regional Industrial Production",
        description="Year-on-year change in industrial / manufacturing production for 10 Asian economies.",
        series_ids=[
            "regional_ipi_cn",
            "regional_ipi_in",
            "regional_ipi_id",
            "regional_ipi_jp",
            "regional_ipi_my",
            "regional_ipi_ph",
            "regional_ipi_kr",
            "regional_ipi_tw",
            "regional_ipi_th",
            "regional_ipi_vn",
        ],
        google_sheet_series=[],
        sheet_keywords=["industrial production", "ipi"],
    ),

    # ==================================================================
    # REGIONAL — Per-country Import Price Index (YoY) and Producer Price
    # Index (YoY). One node per country per series so the Regional
    # Prices → IPI/PPI sub-tab can render 10 single-line chart cards.
    # Source series_id are derived by src/derived_series.compute_regional_imp_pi_ppi_yoy()
    # from the raw CEIC fetches in series_config.py.
    # ==================================================================
    # ── Import Price Index (per-country YoY) ──
    "regional_imp_pi_yoy_cn": node(
        label="China Import Price Index YoY",
        description="China import prices — year-on-year, from CEIC's HS2-aggregated import trade index.",
        series_ids=["regional_imp_pi_yoy_cn"],
    ),
    "regional_imp_pi_yoy_in": node(
        label="India Import Price Index YoY",
        description="India import prices — year-on-year, derived from CEIC's commodity-level import price index.",
        series_ids=["regional_imp_pi_yoy_in"],
    ),
    "regional_imp_pi_yoy_jp": node(
        label="Japan Import Price Index YoY",
        description="Japan import prices — year-on-year, derived from the BoJ Import Price Index (yen basis).",
        series_ids=["regional_imp_pi_yoy_jp"],
    ),
    "regional_imp_pi_yoy_kr": node(
        label="South Korea Import Price Index YoY",
        description="South Korea import prices — year-on-year, derived from the BoK Import Price Index (won basis).",
        series_ids=["regional_imp_pi_yoy_kr"],
    ),
    "regional_imp_pi_yoy_tw": node(
        label="Taiwan Import Price Index YoY",
        description="Taiwan import prices — year-on-year, derived from the DGBAS Import Price Index (NTD basis).",
        series_ids=["regional_imp_pi_yoy_tw"],
    ),
    "regional_imp_pi_yoy_my": node(
        label="Malaysia Import Price Index YoY",
        description="Malaysia import prices — year-on-year, derived from DOSM's Import Unit Value Index (total).",
        series_ids=["regional_imp_pi_yoy_my"],
    ),
    "regional_imp_pi_yoy_id": node(
        label="Indonesia Import Price Index YoY",
        description="Indonesia import prices — year-on-year, derived from BPS's commodity-level import price index.",
        series_ids=["regional_imp_pi_yoy_id"],
    ),
    "regional_imp_pi_yoy_ph": node(
        label="Philippines Import Price Index YoY",
        description="Philippines import prices — year-on-year, derived from PSA's commodity-level import price index.",
        series_ids=["regional_imp_pi_yoy_ph"],
    ),
    "regional_imp_pi_yoy_th": node(
        label="Thailand Import Price Index YoY",
        description="Thailand import prices — year-on-year, derived from the Bank of Thailand Import Price Index (USD basis).",
        series_ids=["regional_imp_pi_yoy_th"],
    ),
    "regional_imp_pi_yoy_vn": node(
        label="Vietnam Import Price Index YoY",
        description="Vietnam import prices — year-on-year, derived from the GSO commodity-level import price index.",
        series_ids=["regional_imp_pi_yoy_vn"],
    ),

    # ── Producer Price Index (per-country YoY) ──
    "regional_ppi_yoy_cn": node(
        label="China Producer Price Index YoY",
        description="China factory-gate prices — year-on-year, derived from the NBS Producer Price Index.",
        series_ids=["regional_ppi_yoy_cn"],
    ),
    "regional_ppi_yoy_in": node(
        label="India Producer Price Index YoY",
        description="India producer/wholesale prices — year-on-year, derived from the Wholesale Price Index (India's PPI proxy).",
        series_ids=["regional_ppi_yoy_in"],
    ),
    "regional_ppi_yoy_jp": node(
        label="Japan Producer Price Index YoY",
        description="Japan producer prices — year-on-year, derived from the BoJ Producer Price Index.",
        series_ids=["regional_ppi_yoy_jp"],
    ),
    "regional_ppi_yoy_kr": node(
        label="South Korea Producer Price Index YoY",
        description="South Korea producer prices — year-on-year, derived from the BoK Producer Price Index.",
        series_ids=["regional_ppi_yoy_kr"],
    ),
    "regional_ppi_yoy_tw": node(
        label="Taiwan Producer Price Index YoY",
        description="Taiwan producer prices — year-on-year, derived from the DGBAS Producer Price Index.",
        series_ids=["regional_ppi_yoy_tw"],
    ),
    "regional_ppi_yoy_my": node(
        label="Malaysia Producer Price Index YoY",
        description="Malaysia producer prices — year-on-year, derived from DOSM's PPI for local production.",
        series_ids=["regional_ppi_yoy_my"],
    ),
    "regional_ppi_yoy_id": node(
        label="Indonesia Producer Price Index YoY",
        description="Indonesia producer/wholesale prices — year-on-year, from BPS's Wholesale Price Index (general).",
        series_ids=["regional_ppi_yoy_id"],
    ),
    "regional_ppi_yoy_ph": node(
        label="Philippines Producer Price Index YoY",
        description="Philippines producer prices — year-on-year, derived from the PSA Producer Price Index.",
        series_ids=["regional_ppi_yoy_ph"],
    ),
    "regional_ppi_yoy_th": node(
        label="Thailand Producer Price Index YoY",
        description="Thailand producer prices — year-on-year, derived from the Ministry of Commerce Producer Price Index.",
        series_ids=["regional_ppi_yoy_th"],
    ),
    "regional_ppi_yoy_vn": node(
        label="Vietnam Producer Price Index YoY",
        description="Vietnam producer prices — year-on-year, from the GSO's industrial PPI (all items).",
        series_ids=["regional_ppi_yoy_vn"],
    ),
}


ROOT_NODES = [
    "crude_oil",
    "natural_gas",
]
