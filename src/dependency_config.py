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
        description="Global crude benchmarks — the primary channel through which an Iran conflict transmits price shocks.",
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
    "natural_gas": node(
        label="Natural Gas",
        description="Global gas benchmarks — Iran/Gulf disruption affects LNG flows, pipeline gas, and downstream fertiliser and power costs.",
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
        description="Bunker fuel prices (VLSFO, 380cst) — cost driver for shipping and bunkering activity.",
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
        description="Aviation fuel prices — cost driver for airlines and air freight.",
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
        description="Road fuel prices — cost driver for land transport and logistics.",
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
        description="Key petrochemical feedstock — price drives cracker economics and downstream chemical costs.",
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
        description="Ethylene, propylene, polyethylene — intermediate chemicals whose costs feed into manufacturing sectors.",
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
        description="Urea and ammonia prices — gas-derived via Haber-Bosch process; cost driver for agriculture and food.",
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
        description="Port throughput and cargo volumes — affected by marine fuel costs.",
        series_ids=[
            "sea_cargo_handled",
            "container_throughput",
        ],
        google_sheet_series=[],
        sheet_keywords=["shipping", "container", "cargo"],
    ),
    "air_transport": node(
        label="Air Transport",
        description="Flight movements, passenger traffic, air freight — affected by jet fuel costs.",
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
        description="Road transport activity — affected by diesel and petrol costs.",
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
        description="Refinery output — directly affected by crude oil costs and margins.",
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
        description="Petrochemical production — affected by naphtha/LPG feedstock costs and olefin prices.",
        children=["sg_producer_prices"],
        series_ids=["ipi_petrochemicals"],
        google_sheet_series=[],
        sheet_keywords=["petrochemical", "polymer"],
    ),
    "basic_chemicals": node(
        label="Specialty and other chemicals",
        description="Industrial production indices for specialty chemicals (paints, coatings, adhesives) and other chemicals (basic intermediates). Both downstream of crude/naphtha — capture how upstream feedstock cost pressure propagates through the chemicals value chain.",
        series_ids=["ipi_specialty_chemicals", "ipi_other_chemicals"],
        google_sheet_series=[],
        sheet_keywords=["chemical", "methanol", "ammonia", "caustic"],
    ),
    "gas_electricity": node(
        label="Electricity tariff (households)",
        description="Low-tension domestic electricity tariff. Almost all of Singapore's power generation runs on imported natural gas, so the tariff lags but tracks LNG and pipeline-gas prices — the household-facing channel for Middle East gas-supply disruption.",
        children=["sg_cpi", "sg_supply_prices"],
        series_ids=["singstat_electricity_tariff"],
        google_sheet_series=[],
        sheet_keywords=["power", "electricity", "gas"],
    ),

    # ── Wholesale ──
    "wholesale": node(
        label="Wholesale trade",
        description="Foreign Wholesale Trade Index — overall plus the petroleum, chemicals, and ship-chandlers/bunkering subsectors. Direct gauge of how upstream cost shocks pass through to wholesale activity at the Port of Singapore.",
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
        description="Construction-sector activity — value of contracts awarded plus physical-volume demand for cement, steel, and granite. Direct gauge of building activity; cement and steel demand are sensitive to upstream energy-cost pressure since both are energy-intensive to produce.",
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
        description="Monthly prices of key construction materials — cement, steel bars, granite, and concreting sand. Direct passthrough channel for upstream chemicals and energy cost pressure into the building cost base.",
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
        description="Property-market activity — indirectly exposed to upstream cost shocks via construction-cost passthrough and utility-price moves.",
        series_ids=[
            "ceic_property_price_index",
            "ceic_residential_transactions",
        ],
        google_sheet_series=[],
        sheet_keywords=["property", "real estate"],
    ),
    "food_beverage": node(
        label="Food and beverage services",
        description="F&B Services Index — overall sector plus the five segments (restaurants, fast food, caterers, food courts, cafes). Captures how imported food-input cost pressure (driven by fertiliser, packaging, and transport costs) flows through to consumer-facing F&B activity.",
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
        description="Headline CPI and MAS Core inflation — the broadest measure of how energy and imported-input cost shocks reach Singapore households.",
        series_ids=["ceic_cpi_yoy", "ceic_cpi_mom", "ceic_mas_core_inflation", "mas_core_inflation_mom"],
        google_sheet_series=[],
        sheet_keywords=["cpi", "inflation"],
    ),
    "sg_supply_prices": node(
        label="Domestic supply prices",
        description="Prices of goods supplied to the Singapore market — split into oil and non-oil components. Sits upstream of CPI in the price chain; oil component reacts directly to crude-oil cost shocks.",
        series_ids=["ceic_dspi_oil", "ceic_dspi_non_oil"],
        google_sheet_series=[],
        sheet_keywords=["supply price", "dspi"],
    ),
    "sg_producer_prices": node(
        label="Producer prices",
        description="Factory-gate prices for goods manufactured in Singapore (excludes imports), split into oil and non-oil. Captures how upstream cost pressure shows up before retail-level inflation.",
        series_ids=["ceic_mppi_oil", "ceic_mppi_non_oil"],
        google_sheet_series=[],
        sheet_keywords=["producer price", "mppi"],
    ),
    "sg_import_prices": node(
        label="Import prices",
        description="Prices of imports landing in Singapore — split into oil, non-oil, and food components. Direct gauge of imported cost-push pressure during Middle East supply disruptions.",
        series_ids=["ceic_ipi_oil", "ceic_ipi_non_oil", "ceic_ipi_food"],
        google_sheet_series=[],
        sheet_keywords=["import price"],
    ),
    "sg_export_prices": node(
        label="Export prices",
        description="Prices Singapore exporters charge overseas buyers — split into oil and non-oil. Reveals how much upstream cost shocks are passed through to external customers, and signals export competitiveness.",
        series_ids=["ceic_epi_oil", "ceic_epi_non_oil"],
        google_sheet_series=[],
        sheet_keywords=["export price"],
    ),

    # ==================================================================
    # REGIONAL — Asia ex-Singapore CPI and Industrial Production
    # ==================================================================
    "regional_cpi_headline": node(
        label="Regional Headline CPI",
        description="Year-on-year headline CPI inflation across 10 Asian economies — broadest pass-through gauge for Iran/Hormuz energy shocks.",
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
        description="Year-on-year core CPI inflation (excluding food and energy) across the same 10 economies — strips out the direct shock to isolate second-round pass-through.",
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
        description="Year-on-year change in industrial / manufacturing production for 10 Asian economies — real-side activity gauge that captures hits to manufacturing from energy and input cost shocks.",
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
}


ROOT_NODES = [
    "crude_oil",
    "natural_gas",
]
