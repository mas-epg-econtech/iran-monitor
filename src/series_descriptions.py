"""
Friendly names and brief plain-language descriptions for time-series.

Used by the renderer to:
  - Replace long technical legend labels with shorter friendly names
    (e.g., "Jet Fuel NWE FOB Barges" → "NWE FOB Barges").
  - Promote the friendly name into the chart title for single-series charts
    (e.g., "Jet Fuel — NWE FOB Barges" instead of "Jet Fuel — USD/metric tonne").
  - Replace the generic node description with a series-specific one explaining
    what's actually being plotted in plain language.

Lookup strategy: `lookup(series_id, series_name)` tries series_id first (most
stable for short IDs), then series_name (fallback for series whose IDs are
truncated to 64 chars in the DB but whose names are intact). A handful of
entries are keyed by series_id — notably the Motorist scraped pump prices,
whose series_name rotates depending on which station was scraped last.

Editorial style: keep descriptions to one sentence, accessible to a reader who
isn't a commodity-markets specialist. Mention geography + product + market role.
"""

# 2026-04-30: enable PEP 604 (X | Y) annotation syntax under Python 3.9.
from __future__ import annotations

SERIES_DESCRIPTIONS: dict[str, dict[str, str]] = {

    # ════════════════════════════════════════════════════════════════════
    # GLOBAL ENERGY (Tier 1-3 nodes on the Global Shocks page)
    # ════════════════════════════════════════════════════════════════════

    # ── Crude oil ────────────────────────────────────────────────────────
    "Crude Oil": {
        "name": "Brent",
        "desc": "ICE Brent crude futures — the most-traded global oil benchmark; tracks waterborne crude into Europe and Asia.",
    },
    "Crude Oil: WTI": {
        "name": "WTI",
        "desc": "NYMEX West Texas Intermediate crude futures — the US crude benchmark; typically trades at a few-dollar discount to Brent.",
    },

    # ── Natural gas ──────────────────────────────────────────────────────
    "US Natural Gas": {
        "name": "US (Henry Hub)",
        "desc": "Henry Hub natural gas — the US benchmark price; sensitive to US production and weather.",
    },
    "Germany Natural Gas": {
        "name": "Germany",
        "desc": "European gas import price (Germany border) — proxy for the European TTF benchmark; sensitive to Russian pipeline and LNG flows.",
    },

    # ── Marine fuel ──────────────────────────────────────────────────────
    "ClearLynx VLSFO Bunker Fuel Spot Price/Singapore": {
        "name": "VLSFO Singapore",
        "desc": "Very Low Sulphur Fuel Oil at Singapore — the post-IMO-2020 marine bunker standard, priced at the world's largest bunkering hub.",
    },
    "Asia Fuel Oil 380cst FOB Singapore Cargo Spot": {
        "name": "380cst Singapore",
        "desc": "High-sulphur 380-centistoke fuel oil at Singapore — used by ships fitted with scrubbers; spread vs VLSFO is a refining-margin signal.",
    },

    # ── Jet fuel ─────────────────────────────────────────────────────────
    "Jet Fuel NWE FOB Barges": {
        "name": "NWE FOB Barges",
        "desc": "Northwest Europe jet fuel sold off-barge at Rotterdam — the main European jet fuel benchmark.",
    },
    "Jet Fuel Singapore FOB Cargoes vs Crude Oil Dated Brent FOB NWE": {
        "name": "Singapore vs Brent crack",
        "desc": "Singapore jet fuel cargoes priced as a premium/discount to Brent crude — proxy for Asian jet refining margins (\"crack spread\").",
    },
    "PADD I Average Jet Fuel Spot Market Price Prompt": {
        "name": "PADD 1 (US East Coast)",
        "desc": "Wholesale jet fuel spot price for the US East Coast (PADD 1) — major US jet consumption region.",
    },

    # ── Gasoline / diesel ────────────────────────────────────────────────
    "Gasoline Singapore 92 RON FOB Cargoes": {
        "name": "Singapore 92 RON",
        "desc": "Singapore-traded 92-octane gasoline cargoes — Asian regional gasoline benchmark.",
    },
    "Gasoline Singapore 95 RON FOB Cargoes": {
        "name": "Singapore 95 RON",
        "desc": "Singapore-traded 95-octane gasoline cargoes — higher-grade Asian gasoline.",
    },
    "RBOB Regular Gasoline NY Buckeye Continuous MKTMID": {
        "name": "RBOB (US)",
        "desc": "NYMEX RBOB reformulated blendstock — US gasoline futures benchmark.",
    },

    # ── Naphtha (petrochemical feedstock) ────────────────────────────────
    "Naphtha Japan CIF Cargoes": {
        "name": "Japan CIF",
        "desc": "Naphtha delivered to Japan — main Asian petrochemical-cracker feedstock benchmark.",
    },
    "Naphtha Singapore FOB Cargoes": {
        "name": "Singapore FOB",
        "desc": "Naphtha at Singapore — regional cracker feedstock benchmark.",
    },
    "GX Naphtha NWE CIF Cargoes Prompt": {
        "name": "NWE CIF",
        "desc": "Naphtha delivered to Northwest Europe — European cracker feedstock benchmark.",
    },
    "Japan Naphtha": {
        "name": "Japan (CEIC monthly)",
        "desc": "Japan naphtha monthly average price (CEIC).",
    },
    "France Naphtha": {
        "name": "France (CEIC monthly)",
        "desc": "France naphtha monthly average price (CEIC).",
    },

    # ── LPG (alternative cracker feedstock) ──────────────────────────────
    "North American Spot LPGs/NGLs Propane Price/Mont Belvieu LST": {
        "name": "Propane (Mont Belvieu)",
        "desc": "US propane spot price at Mont Belvieu, Texas — the main US LPG storage and trading hub.",
    },
    "North American Spot LPGs/NGLs Normal Butane Price/Mont Belvieu LST": {
        "name": "Butane (Mont Belvieu)",
        "desc": "US normal-butane spot price at Mont Belvieu, Texas.",
    },
    "North American Spot LPGs/NGLs Purity Ethane Price/Mont Belvieu non-LST": {
        "name": "Ethane (Mont Belvieu)",
        "desc": "US purity-ethane spot price at Mont Belvieu — primary feedstock for US ethylene crackers.",
    },
    "Bloomberg Arab Gulf LPG Propane Monthly Posted Price": {
        "name": "Arab Gulf Propane",
        "desc": "Saudi Aramco's monthly contract propane price — the Asian LPG benchmark; sets contract pricing across the East of Suez market.",
    },
    "Bloomberg Arab Gulf LPG Butane Monthly Posted Price": {
        "name": "Arab Gulf Butane",
        "desc": "Saudi Aramco's monthly contract butane price — Asian LPG benchmark.",
    },

    # ── Olefins (cracker outputs) ────────────────────────────────────────
    "NE Asia Ethylene (Olefins) CFR Spot Price Weekly": {
        "name": "NE Asia ethylene",
        "desc": "Northeast Asia ethylene spot price — primary cracker output; feedstock for downstream polymers.",
    },
    "SE Asia Ethylene (Olefins) CFR Spot Price Weekly": {
        "name": "SE Asia ethylene",
        "desc": "Southeast Asia ethylene spot price — closest cracker-output benchmark to Singapore.",
    },
    "NWE Ethylene CIF Price USD/MT Weekly": {
        "name": "NWE ethylene",
        "desc": "Northwest Europe ethylene delivered price — European cracker-output benchmark.",
    },
    "US Gulf Ethylene (Olefins) FD Spot Price Weekly": {
        "name": "US Gulf ethylene",
        "desc": "US Gulf Coast ethylene — world's largest cracker hub; ethane-based, often the global low-cost producer.",
    },

    # ── Polymers (downstream of olefins) ─────────────────────────────────
    "China Chemicals SunSirs HDPE High Density Polyethylene": {
        "name": "China HDPE",
        "desc": "China high-density polyethylene — used in pipes, bottles, and rigid packaging; bellwether for Chinese plastics demand.",
    },
    "China Chemicals SunSirs LLDPE Linear Low-Density Polyethylene": {
        "name": "China LLDPE",
        "desc": "China linear low-density polyethylene — film and packaging resin.",
    },
    "China Chemicals SunSirs PET Polyethylene Terephthalate": {
        "name": "China PET",
        "desc": "China polyethylene terephthalate — bottle and synthetic-fibre resin.",
    },
    "SE Asia Film-Grade Polyethylene (HDPE Polymers) CFR Spot Price Weekly": {
        "name": "SE Asia HDPE film",
        "desc": "Southeast Asia film-grade HDPE — packaging-bag resin benchmark for the region.",
    },
    "SE Asia Film-Grade Polyethylene (LLDPE Polymers) CFR Spot Price Weekly": {
        "name": "SE Asia LLDPE film",
        "desc": "Southeast Asia film-grade LLDPE — packaging-film resin benchmark for the region.",
    },

    # ── Fertilisers ──────────────────────────────────────────────────────
    "Urea Price: US Gulf (IMF)": {
        "name": "Urea (US Gulf)",
        "desc": "US Gulf urea spot price (IMF series) — global agricultural-input benchmark; nitrogen fertiliser made from natural gas via the Haber-Bosch process.",
    },

    # ════════════════════════════════════════════════════════════════════
    # SINGAPORE — DOMESTIC PRICES
    # ════════════════════════════════════════════════════════════════════

    # ── SG retail fuel (SingStat monthly) ────────────────────────────────
    "Retail Prices: Petrol, 92 Octane (SingStat)": {
        "name": "92 RON",
        "desc": "SingStat monthly average retail price for 92-octane petrol across Singapore stations.",
    },
    "Retail Prices: Petrol, 95 Octane (SingStat)": {
        "name": "95 RON",
        "desc": "SingStat monthly average retail price for 95-octane petrol.",
    },
    "Retail Prices: Petrol, 98 Octane (SingStat)": {
        "name": "98 RON",
        "desc": "SingStat monthly average retail price for 98-octane petrol.",
    },
    "Retail Prices: Diesel (SingStat)": {
        "name": "Diesel",
        "desc": "SingStat monthly average retail price for diesel.",
    },

    # ── SG pump prices (Motorist daily scrape — keyed by series_id since
    #    series_name rotates with whichever station was scraped) ──────────
    "motorist_92": {
        "name": "92 RON pump",
        "desc": "Daily-scraped 92-octane pump price (brand varies day-to-day with the scraped sample).",
    },
    "motorist_95": {
        "name": "95 RON pump",
        "desc": "Daily-scraped 95-octane pump price.",
    },
    "motorist_98": {
        "name": "98 RON pump",
        "desc": "Daily-scraped 98-octane pump price.",
    },
    "motorist_premium": {
        "name": "Premium pump",
        "desc": "Daily-scraped premium-grade pump price.",
    },
    "motorist_diesel": {
        "name": "Diesel pump",
        "desc": "Daily-scraped diesel pump price.",
    },

    # ── SG headline inflation ────────────────────────────────────────────
    # Friendly names omit the YoY/MoM suffix because the charts are split by
    # unit, so the Y-axis already shows whether it's annual or monthly.
    "CPI All Items YoY": {
        "name": "Headline CPI",
        "desc": "Year-on-year change in the Singapore Consumer Price Index — the broadest measure of consumer inflation.",
    },
    "CPI All Items MoM": {
        "name": "Headline CPI",
        "desc": "Month-on-month change in the Singapore Consumer Price Index.",
    },
    "MAS Core Inflation YoY": {
        "name": "MAS Core CPI",
        "desc": "MAS measure of core inflation, excluding accommodation and private road transport — preferred policy gauge.",
    },
    "MAS Core Inflation MoM": {
        "name": "MAS Core CPI",
        "desc": "Month-on-month change in MAS Core Inflation — derived from the level index since MAS doesn't publish MoM directly.",
    },
    "MAS Core Inflation Index": {
        "name": "MAS Core (level)",
        "desc": "MAS Core Inflation Index (2024=100) — the underlying level series; MoM is derived from this.",
    },

    # ── SG Domestic Supply Prices ────────────────────────────────────────
    "Domestic Supply Price Index (Oil)": {
        "name": "Oil",
        "desc": "Oil component of domestic supply prices — upstream cost pressure on oil-based goods supplied in Singapore.",
    },
    "Domestic Supply Price Index (Non-oil)": {
        "name": "Non-oil",
        "desc": "Non-oil component of domestic supply prices.",
    },

    # ── SG Import Prices ─────────────────────────────────────────────────
    "Import Price Index (Oil)": {
        "name": "Oil",
        "desc": "Cost of oil imports into Singapore.",
    },
    "Import Price Index (Non-oil)": {
        "name": "Non-oil",
        "desc": "Cost of non-oil imports into Singapore.",
    },
    "Import Price Index (Food & Live Animals)": {
        "name": "Food",
        "desc": "Cost of food and live-animal imports into Singapore.",
    },

    # ── SG Export Prices ─────────────────────────────────────────────────
    "Export Price Index (Oil)": {
        "name": "Oil",
        "desc": "Sales prices of Singapore's refined-product exports.",
    },
    "Export Price Index (Non-oil)": {
        "name": "Non-oil",
        "desc": "Sales prices of Singapore's non-oil exports.",
    },

    # ── SG Producer Prices ───────────────────────────────────────────────
    "Manufactured Producers Price Index (Oil)": {
        "name": "Oil",
        "desc": "Factory-gate prices for petroleum products manufactured in Singapore.",
    },
    "Manufactured Producers Price Index (Non-oil)": {
        "name": "Non-oil",
        "desc": "Factory-gate prices for non-oil goods manufactured in Singapore.",
    },

    # ── Electricity ──────────────────────────────────────────────────────
    "Electricity Tariff: Low Tension Domestic": {
        "name": "Domestic tariff",
        "desc": "Low-tension domestic electricity tariff — the household electricity rate in Singapore (cents per kWh).",
    },

    # ════════════════════════════════════════════════════════════════════
    # SINGAPORE — SECTORAL ACTIVITY
    # ════════════════════════════════════════════════════════════════════

    # ── Petroleum refining ───────────────────────────────────────────────
    # NB: official SingStat name is "Index of Industrial Production" → IIP.
    # As of the M355381 migration the DB labels are now "IIP: ...".
    "IIP: Petroleum": {
        "name": "IIP",
        "desc": "Index of Industrial Production for petroleum refining — captures throughput of Singapore's refineries.",
    },
    "Singapore Imports: Petroleum (SingStat)": {
        "name": "Petroleum imports",
        "desc": "Singapore's monthly petroleum imports (SingStat) — value in SGD.",
    },
    "Singapore Exports: Petroleum (SingStat)": {
        "name": "Petroleum exports",
        "desc": "Singapore's monthly petroleum exports (SingStat) — value in SGD.",
    },

    # ── Petrochemicals / chemicals ───────────────────────────────────────
    "IIP: Petrochemicals": {
        "name": "IIP",
        "desc": "Index of Industrial Production for petrochemicals — output of Singapore's petrochemical complex (mainly Jurong Island).",
    },
    # 2026-04-30: replaced "IIP: Chemicals Cluster" + old SingStat Specialty
    # Chemicals with two CEIC IIPs (Specialty + Other Chem).
    "IIP: Specialty Chemicals": {
        "name": "Specialty Chem",
        "desc": "Index of Industrial Production for specialty chemicals — high-margin specialty inputs (paints, coatings, adhesives, etc.).",
    },
    "IIP: Other Chemicals": {
        "name": "Other Chem",
        "desc": "Index of Industrial Production for other chemicals — non-specialty industrial chemicals (basic, intermediate).",
    },

    # ── Wholesale (Foreign Wholesale Trade Index, monthly, 2017=100) ─────
    "Foreign Wholesale Trade Index — Overall": {
        "name": "Overall",
        "desc": "Foreign Wholesale Trade Index — overall foreign wholesale trade activity at 2017=100.",
    },
    "Foreign Wholesale Trade Index — Petroleum and Petroleum Products": {
        "name": "Petroleum & PP",
        "desc": "Foreign Wholesale Trade Index — petroleum and petroleum products subsector. Direct exposure to upstream energy cost shocks.",
    },
    "Foreign Wholesale Trade Index — Chemical and Chemical Products": {
        "name": "Chemical & CP",
        "desc": "Foreign Wholesale Trade Index — chemical and chemical products subsector. Reflects passthrough from feedstock to wholesale margins.",
    },
    "Foreign Wholesale Trade Index — Ship Chandlers and Bunkering": {
        "name": "Bunkering",
        "desc": "Foreign Wholesale Trade Index — ship chandlers and bunkering. Direct gauge of marine-fuel volumes at the Port of Singapore.",
    },

    # ── Construction (contracts + materials demand + materials prices) ──
    "Construction Contracts Awarded (Total)": {
        "name": "Contracts awarded",
        "desc": "Monthly value of construction contracts awarded — leading indicator of construction-sector activity.",
    },
    "Construction Materials Demand: Cement": {
        "name": "Cement",
        "desc": "Monthly cement demand — physical volume used in construction.",
    },
    "Construction Materials Demand: Steel Bars": {
        "name": "Steel bars",
        "desc": "Monthly steel-bar demand.",
    },
    "Construction Materials Demand: Granite": {
        "name": "Granite",
        "desc": "Monthly granite demand — aggregate input for concrete.",
    },
    # 2026-04-30: ready-mixed concrete (demand + price) dropped per dashboard feedback.
    "Construction Materials Price: Cement": {
        "name": "Cement",
        "desc": "Monthly cement price (SGD/ton).",
    },
    "Construction Materials Price: Steel Bars": {
        "name": "Steel bars",
        "desc": "Monthly steel-bar price (SGD/ton).",
    },
    "Construction Materials Price: Granite": {
        "name": "Granite",
        "desc": "Monthly granite price (SGD/ton).",
    },
    "Construction Materials Price: Concreting Sand": {
        "name": "Concreting sand",
        "desc": "Monthly concreting sand price (SGD/ton).",
    },

    # ── Real estate ──────────────────────────────────────────────────────
    "Property Price Index: Private Residential (URA)": {
        "name": "Private property PPI",
        "desc": "URA Private Residential Property Price Index — quarterly benchmark for non-HDB housing prices.",
    },
    "Residential Property Transactions: Deals (URA)": {
        "name": "Property Deals (Developer sales and resales)",
        "desc": "URA monthly count of private residential property transactions — combines developer sales and resales. Proxy for buyer activity.",
    },

    # ── Food & beverage (chained-volume index, 2017=100) ─────────────────
    # 2026-04-30: replaced single food_and_beverage_sales with 6-segment series.
    "F&B Services Index — Overall": {
        "name": "Overall",
        "desc": "F&B Services Index (chained-volume) — overall sector activity at 2017=100.",
    },
    "F&B Services Index — Restaurants": {
        "name": "Restaurants",
        "desc": "F&B Services Index — restaurants segment.",
    },
    "F&B Services Index — Fast Food Outlets": {
        "name": "Fast food",
        "desc": "F&B Services Index — fast food outlets segment.",
    },
    "F&B Services Index — Food Caterers": {
        "name": "Caterers",
        "desc": "F&B Services Index — food caterers segment.",
    },
    "F&B Services Index — Cafes": {
        "name": "Cafes",
        "desc": "F&B Services Index — cafes, coffee houses, snack bars segment.",
    },
    "F&B Services Index — Food Courts": {
        "name": "Food courts",
        "desc": "F&B Services Index — food courts and hawker centres segment.",
    },

    # ── Water transport ──────────────────────────────────────────────────
    "Sea Cargo Handled": {
        "name": "Sea cargo",
        "desc": "Total sea cargo handled at Singapore (thousand tons).",
    },
    "Container Throughput": {
        "name": "Container throughput",
        "desc": "Container throughput at Singapore port (thousand TEU) — real-time gauge of trade flows.",
    },

    # ── Air transport ────────────────────────────────────────────────────
    "Flight Movements": {
        "name": "Flight movements",
        "desc": "Total commercial flight movements at Changi (arrivals + departures).",
    },
    "Passenger Movements": {
        "name": "Passenger movements",
        "desc": "Total passenger movements at Changi (arrivals + departures + transit).",
    },
    "Air Freight Movements": {
        "name": "Air freight",
        "desc": "Air freight tonnage handled at Changi.",
    },

    # ── Land transport ───────────────────────────────────────────────────
    "Visitor Arrivals by Land": {
        "name": "Land visitor arrivals",
        "desc": "Cross-border visitor arrivals by land — proxy for Causeway and Tuas Second Link activity.",
    },

    # ════════════════════════════════════════════════════════════════════
    # REGIONAL — FINANCIAL MARKETS
    # ════════════════════════════════════════════════════════════════════

    # ── ASEAN FX (per USD) ───────────────────────────────────────────────
    "Indonesian Rupiah": {
        "name": "IDR/USD",
        "desc": "Indonesian Rupiah per US Dollar (Yahoo Finance mid-rate).",
    },
    "Malaysian Ringgit": {
        "name": "MYR/USD",
        "desc": "Malaysian Ringgit per US Dollar.",
    },
    "Philippine Peso": {
        "name": "PHP/USD",
        "desc": "Philippine Peso per US Dollar.",
    },
    "Thai Baht": {
        "name": "THB/USD",
        "desc": "Thai Baht per US Dollar.",
    },
    "Vietnamese Dong": {
        "name": "VND/USD",
        "desc": "Vietnamese Dong per US Dollar.",
    },

    # ── Sovereign 10Y yields ─────────────────────────────────────────────
    "US 10Y Treasury Yield": {
        "name": "US 10Y",
        "desc": "10-year US Treasury yield — global risk-free benchmark; sets the floor for global rates.",
    },
    "Indonesia 10Y Govt Bond Yield": {
        "name": "Indonesia 10Y",
        "desc": "Indonesia 10-year government bond yield (ADB AsianBondsOnline).",
    },
    "Malaysia 10Y Govt Bond Yield": {
        "name": "Malaysia 10Y",
        "desc": "Malaysia 10-year government bond yield.",
    },
    "Philippines 10Y Govt Bond Yield": {
        "name": "Philippines 10Y",
        "desc": "Philippines 10-year government bond yield.",
    },
    "Thailand 10Y Govt Bond Yield": {
        "name": "Thailand 10Y",
        "desc": "Thailand 10-year government bond yield.",
    },

    # ── Commodities ──────────────────────────────────────────────────────
    "Brent Crude Oil (ICE Futures)": {
        "name": "Brent (ICE)",
        "desc": "Front-month ICE Brent crude futures — global oil benchmark.",
    },
    "JKM LNG Futures (Platts)": {
        "name": "JKM LNG",
        "desc": "Japan-Korea-Marker LNG futures — the Asian LNG spot benchmark.",
    },
    "Thermal Coal (Newcastle FOB)": {
        "name": "Newcastle coal",
        "desc": "Newcastle (Australia) FOB thermal coal — Asian coal benchmark.",
    },
    "Crude Palm Oil (Bursa Malaysia FCPO)": {
        "name": "Crude palm oil",
        "desc": "Bursa Malaysia FCPO front-month palm oil futures — global palm oil benchmark.",
    },
    "Rubber TSR20 Futures (SGX)": {
        "name": "Rubber TSR20",
        "desc": "SGX TSR20 rubber futures — natural rubber benchmark, used in tire manufacturing.",
    },
    "Nickel Futures (LME)": {
        "name": "Nickel (LME)",
        "desc": "LME nickel futures — used in stainless steel and EV batteries; Indonesia is the world's largest producer.",
    },
    "Gold Futures (COMEX)": {
        "name": "Gold (COMEX)",
        "desc": "COMEX gold futures — global safe-haven benchmark.",
    },

    # ════════════════════════════════════════════════════════════════════
    # REGIONAL — CPI Headline (YoY)
    # Per-country charts (one per country) plot headline + core together,
    # so legends use the type ("Headline CPI" / "Core CPI"); the country is
    # already in the chart title.
    # ════════════════════════════════════════════════════════════════════
    "regional_cpi_headline_cn": {"name": "Headline CPI", "desc": "China CPI — year-on-year change in the headline consumer price index (NBS)."},
    "regional_cpi_headline_in": {"name": "Headline CPI", "desc": "India CPI — year-on-year change in the headline consumer price index (MoSPI)."},
    "regional_cpi_headline_id": {"name": "Headline CPI", "desc": "Indonesia CPI — year-on-year change in the headline consumer price index (BPS)."},
    "regional_cpi_headline_jp": {"name": "Headline CPI", "desc": "Japan CPI — year-on-year change in the headline consumer price index (MIC)."},
    "regional_cpi_headline_my": {"name": "Headline CPI", "desc": "Malaysia CPI — year-on-year change in the headline consumer price index (DOSM)."},
    "regional_cpi_headline_ph": {"name": "Headline CPI", "desc": "Philippines CPI — year-on-year change in the headline consumer price index (PSA)."},
    "regional_cpi_headline_kr": {"name": "Headline CPI", "desc": "South Korea CPI — year-on-year change in the headline consumer price index (KOSTAT)."},
    "regional_cpi_headline_tw": {"name": "Headline CPI", "desc": "Taiwan CPI — year-on-year change in the headline consumer price index (DGBAS)."},
    "regional_cpi_headline_th": {"name": "Headline CPI", "desc": "Thailand CPI — year-on-year change in the headline consumer price index (MoC)."},
    "regional_cpi_headline_vn": {"name": "Headline CPI", "desc": "Vietnam CPI — year-on-year change in the headline consumer price index (GSO)."},

    # ════════════════════════════════════════════════════════════════════
    # REGIONAL — CPI Core (YoY)
    # ════════════════════════════════════════════════════════════════════
    "regional_cpi_core_cn": {"name": "Core CPI", "desc": "China core CPI — year-on-year change excluding food and energy."},
    "regional_cpi_core_in": {"name": "Core CPI", "desc": "India core CPI — year-on-year change excluding food and fuel & light."},
    "regional_cpi_core_id": {"name": "Core CPI", "desc": "Indonesia core CPI — year-on-year change excluding administered prices and volatile foods."},
    "regional_cpi_core_jp": {"name": "Core CPI", "desc": "Japan core CPI — year-on-year change excluding fresh food and energy (BoJ's preferred core gauge)."},
    "regional_cpi_core_my": {"name": "Core CPI", "desc": "Malaysia core CPI — year-on-year change excluding fresh food and administered prices."},
    "regional_cpi_core_ph": {"name": "Core CPI", "desc": "Philippines core CPI — year-on-year change excluding selected food and energy items."},
    "regional_cpi_core_kr": {"name": "Core CPI", "desc": "South Korea core CPI — year-on-year change excluding food and energy."},
    "regional_cpi_core_tw": {"name": "Core CPI", "desc": "Taiwan core CPI — year-on-year change excluding fruits, vegetables, and energy."},
    "regional_cpi_core_th": {"name": "Core CPI", "desc": "Thailand core CPI — year-on-year change excluding raw food and energy."},
    "regional_cpi_core_vn": {"name": "Core CPI", "desc": "Vietnam core CPI — year-on-year change excluding food, energy, and state-managed items."},

    # ════════════════════════════════════════════════════════════════════
    # REGIONAL — Industrial Production YoY %
    # All 10 share unit % YoY. Friendly name = country (used as legend on
    # single-series per-country charts). NB: the precise underlying metric
    # varies by country (NBS Value Added of Industry for China, METI Mining &
    # Mfg IPI for Japan, OECD harmonised series for South Korea, etc.) — they
    # all measure real-side industrial activity but methodologies differ.
    # Source agencies are noted in each card description in page_layouts.py.
    # ════════════════════════════════════════════════════════════════════
    "regional_ipi_cn": {"name": "China",       "desc": "China Value Added of Industry, year-on-year (NBS) — the official PRC headline industrial activity print."},
    "regional_ipi_in": {"name": "India",       "desc": "India industrial production index, year-on-year (MoSPI) — output across mining, manufacturing, and electricity."},
    "regional_ipi_id": {"name": "Indonesia",   "desc": "Indonesia industrial production index, year-on-year (BPS / CEIC computation). Publishes ~3 months in arrears."},
    "regional_ipi_jp": {"name": "Japan",       "desc": "Japan mining & manufacturing IPI, year-on-year (METI)."},
    "regional_ipi_my": {"name": "Malaysia",    "desc": "Malaysia industrial production index, year-on-year (DOSM) — mining, manufacturing, and electricity."},
    "regional_ipi_ph": {"name": "Philippines", "desc": "Philippines IPI volume, year-on-year (PSA) — manufacturing output."},
    "regional_ipi_kr": {"name": "South Korea", "desc": "South Korea total manufacturing production, seasonally-adjusted, year-on-year (OECD harmonised series)."},
    "regional_ipi_tw": {"name": "Taiwan",      "desc": "Taiwan industrial production index, year-on-year (CEIC computation from MOEA)."},
    "regional_ipi_th": {"name": "Thailand",    "desc": "Thailand industrial production index, year-on-year (CEIC computation from OIE)."},
    "regional_ipi_vn": {"name": "Vietnam",     "desc": "Vietnam industrial production index, year-on-year (GSO calculation)."},

    # ════════════════════════════════════════════════════════════════════
    # REGIONAL — Chemical imports from SG (derived from trade_singstat)
    # Two series_ids per country — annual (2023-2025) and monthly (from
    # 2026-01) — rendered as separate bar charts paired per row in the
    # Regional Trade layout.
    # ════════════════════════════════════════════════════════════════════
    "singstat_chem_export_annual_cn": {"name": "China — Annual",       "desc": "China's annual imports of chemicals (excl. organics & pharma) from Singapore (SGD thousands), 2023–25, from SingStat via the dashboard workbook."},
    "singstat_chem_export_annual_in": {"name": "India — Annual",       "desc": "India's annual imports of chemicals (excl. organics & pharma) from Singapore (SGD thousands), 2023–25, from SingStat."},
    "singstat_chem_export_annual_id": {"name": "Indonesia — Annual",   "desc": "Indonesia's annual imports of chemicals (excl. organics & pharma) from Singapore (SGD thousands), 2023–25, from SingStat."},
    "singstat_chem_export_annual_jp": {"name": "Japan — Annual",       "desc": "Japan's annual imports of chemicals (excl. organics & pharma) from Singapore (SGD thousands), 2023–25, from SingStat."},
    "singstat_chem_export_annual_my": {"name": "Malaysia — Annual",    "desc": "Malaysia's annual imports of chemicals (excl. organics & pharma) from Singapore (SGD thousands), 2023–25, from SingStat."},
    "singstat_chem_export_annual_ph": {"name": "Philippines — Annual", "desc": "Philippines' annual imports of chemicals from Singapore (SGD thousands), 2023–25, from SingStat."},
    "singstat_chem_export_annual_kr": {"name": "South Korea — Annual", "desc": "South Korea's annual imports of chemicals (excl. organics & pharma) from Singapore (SGD thousands), 2023–25, from SingStat."},
    "singstat_chem_export_annual_tw": {"name": "Taiwan — Annual",      "desc": "Taiwan's annual imports of chemicals (excl. organics & pharma) from Singapore (SGD thousands), 2023–25, from SingStat."},
    "singstat_chem_export_annual_th": {"name": "Thailand — Annual",    "desc": "Thailand's annual imports of chemicals (excl. organics & pharma) from Singapore (SGD thousands), 2023–25, from SingStat."},
    "singstat_chem_export_annual_vn": {"name": "Vietnam — Annual",     "desc": "Vietnam's annual imports of chemicals (excl. organics & pharma) from Singapore (SGD thousands), 2023–25, from SingStat."},

    # Friendly names match the corresponding `sg_chem_export_share_*` series
    # (just country names) so the shares chart + levels chart on the
    # combined card share one legend.
    "singstat_chem_export_monthly_cn": {"name": "China",       "desc": "China's monthly imports of chemicals (excl. organics & pharma) from Singapore (SGD thousands), 2026, from SingStat. New months added as published."},
    "singstat_chem_export_monthly_in": {"name": "India",       "desc": "India's monthly imports of chemicals (excl. organics & pharma) from Singapore (SGD thousands), 2026, from SingStat."},
    "singstat_chem_export_monthly_id": {"name": "Indonesia",   "desc": "Indonesia's monthly imports of chemicals (excl. organics & pharma) from Singapore (SGD thousands), 2026, from SingStat."},
    "singstat_chem_export_monthly_jp": {"name": "Japan",       "desc": "Japan's monthly imports of chemicals (excl. organics & pharma) from Singapore (SGD thousands), 2026, from SingStat."},
    "singstat_chem_export_monthly_my": {"name": "Malaysia",    "desc": "Malaysia's monthly imports of chemicals (excl. organics & pharma) from Singapore (SGD thousands), 2026, from SingStat."},
    "singstat_chem_export_monthly_ph": {"name": "Philippines", "desc": "Philippines' monthly imports of chemicals from Singapore (SGD thousands), 2026, from SingStat."},
    "singstat_chem_export_monthly_kr": {"name": "South Korea", "desc": "South Korea's monthly imports of chemicals (excl. organics & pharma) from Singapore (SGD thousands), 2026, from SingStat."},
    "singstat_chem_export_monthly_tw": {"name": "Taiwan",      "desc": "Taiwan's monthly imports of chemicals (excl. organics & pharma) from Singapore (SGD thousands), 2026, from SingStat."},
    "singstat_chem_export_monthly_th": {"name": "Thailand",    "desc": "Thailand's monthly imports of chemicals (excl. organics & pharma) from Singapore (SGD thousands), 2026, from SingStat."},
    "singstat_chem_export_monthly_vn": {"name": "Vietnam",     "desc": "Vietnam's monthly imports of chemicals (excl. organics & pharma) from Singapore (SGD thousands), 2026, from SingStat."},
    # Non-regional residual on the monthly stacked-levels chart.
    "sg_chem_export_monthly_others":   {"name": "Others",      "desc": "Monthly SG industrial-chemical exports to non-regional destinations (mainly US/EU). Total minus the 10 regional countries' sum."},

    # Regional Trade Exposure tab — per-country chemical-imports-from-SG cards.
    # Each card has 1 dataset per chart, so the friendly_name shows up on
    # the legend if not suppressed; using the country name reads cleanly.
    "regional_chem_share_from_sg_cn":     {"name": "China",       "desc": "SG's share of China's annual industrial-chemical imports (SITC 5 − 51 − 54). Source: UN Comtrade, USD basis."},
    "regional_chem_share_from_sg_in":     {"name": "India",       "desc": "SG's share of India's annual industrial-chemical imports (SITC 5 − 51 − 54). Source: UN Comtrade, USD basis."},
    "regional_chem_share_from_sg_id":     {"name": "Indonesia",   "desc": "SG's share of Indonesia's annual industrial-chemical imports (SITC 5 − 51 − 54). Source: UN Comtrade, USD basis."},
    "regional_chem_share_from_sg_jp":     {"name": "Japan",       "desc": "SG's share of Japan's annual industrial-chemical imports (SITC 5 − 51 − 54). Source: UN Comtrade, USD basis."},
    "regional_chem_share_from_sg_kr":     {"name": "South Korea", "desc": "SG's share of South Korea's annual industrial-chemical imports (SITC 5 − 51 − 54). Source: UN Comtrade, USD basis."},
    "regional_chem_share_from_sg_my":     {"name": "Malaysia",    "desc": "SG's share of Malaysia's annual industrial-chemical imports (SITC 5 − 51 − 54). Source: UN Comtrade, USD basis."},
    "regional_chem_share_from_sg_ph":     {"name": "Philippines", "desc": "SG's share of the Philippines' annual industrial-chemical imports (SITC 5 − 51 − 54). Source: UN Comtrade, USD basis."},
    "regional_chem_share_from_sg_tw":     {"name": "Taiwan",      "desc": "SG's share of Taiwan's annual industrial-chemical imports (SITC 5 − 51 − 54). Source: UN Comtrade, USD basis."},
    "regional_chem_share_from_sg_th":     {"name": "Thailand",    "desc": "SG's share of Thailand's annual industrial-chemical imports (SITC 5 − 51 − 54). Source: UN Comtrade, USD basis."},
    "regional_chem_share_from_sg_vn":     {"name": "Vietnam",     "desc": "SG's share of Vietnam's annual industrial-chemical imports (SITC 5 − 51 − 54). Source: UN Comtrade, USD basis."},

    # Per-country monthly levels (alias of singstat_chem_export_monthly_<iso2>
    # so we can stash a per-country benchmark independent of the SG-side card).
    "regional_chem_imports_from_sg_cn":   {"name": "China",       "desc": "China's monthly industrial-chemical imports from Singapore (SGD thousands). Source: SingStat via SG_Chemicals_DX."},
    "regional_chem_imports_from_sg_in":   {"name": "India",       "desc": "India's monthly industrial-chemical imports from Singapore (SGD thousands). Source: SingStat via SG_Chemicals_DX."},
    "regional_chem_imports_from_sg_id":   {"name": "Indonesia",   "desc": "Indonesia's monthly industrial-chemical imports from Singapore (SGD thousands). Source: SingStat via SG_Chemicals_DX."},
    "regional_chem_imports_from_sg_jp":   {"name": "Japan",       "desc": "Japan's monthly industrial-chemical imports from Singapore (SGD thousands). Source: SingStat via SG_Chemicals_DX."},
    "regional_chem_imports_from_sg_kr":   {"name": "South Korea", "desc": "South Korea's monthly industrial-chemical imports from Singapore (SGD thousands). Source: SingStat via SG_Chemicals_DX."},
    "regional_chem_imports_from_sg_my":   {"name": "Malaysia",    "desc": "Malaysia's monthly industrial-chemical imports from Singapore (SGD thousands). Source: SingStat via SG_Chemicals_DX."},
    "regional_chem_imports_from_sg_ph":   {"name": "Philippines", "desc": "Philippines' monthly industrial-chemical imports from Singapore (SGD thousands). Source: SingStat via SG_Chemicals_DX."},
    "regional_chem_imports_from_sg_tw":   {"name": "Taiwan",      "desc": "Taiwan's monthly industrial-chemical imports from Singapore (SGD thousands). Source: SingStat via SG_Chemicals_DX."},
    "regional_chem_imports_from_sg_th":   {"name": "Thailand",    "desc": "Thailand's monthly industrial-chemical imports from Singapore (SGD thousands). Source: SingStat via SG_Chemicals_DX."},
    "regional_chem_imports_from_sg_vn":   {"name": "Vietnam",     "desc": "Vietnam's monthly industrial-chemical imports from Singapore (SGD thousands). Source: SingStat via SG_Chemicals_DX."},

    # ════════════════════════════════════════════════════════════════════
    # SINGAPORE TRADE TAB — derived series for Sections 1-4
    # ════════════════════════════════════════════════════════════════════

    # Singapore Trade Exposure tab — share + monthly series for 6 SITCs ×
    # (6 ME countries + Others residual). The friendly name is the ME
    # country / "Others" label; the renderer's STABLE_PARTNER_COLORS table
    # ensures e.g. Qatar is always green across every chart on the tab.
    "sg_imp_share_sitc_3_ae":   {"name": "UAE",          "desc": "UAE share of SG total mineral fuel imports (SITC 3)."},
    "sg_imp_share_sitc_3_sa":   {"name": "Saudi Arabia", "desc": "Saudi Arabia share of SG total mineral fuel imports (SITC 3)."},
    "sg_imp_share_sitc_3_qa":   {"name": "Qatar",        "desc": "Qatar share of SG total mineral fuel imports (SITC 3)."},
    "sg_imp_share_sitc_3_kw":   {"name": "Kuwait",       "desc": "Kuwait share of SG total mineral fuel imports (SITC 3)."},
    "sg_imp_share_sitc_3_iq":   {"name": "Iraq",         "desc": "Iraq share of SG total mineral fuel imports (SITC 3)."},
    "sg_imp_share_sitc_3_om":   {"name": "Oman",         "desc": "Oman share of SG total mineral fuel imports (SITC 3)."},

    "sg_imp_share_sitc_333_ae": {"name": "UAE",          "desc": "UAE share of SG crude petroleum imports (SITC 333)."},
    "sg_imp_share_sitc_333_sa": {"name": "Saudi Arabia", "desc": "Saudi Arabia share of SG crude petroleum imports (SITC 333)."},
    "sg_imp_share_sitc_333_qa": {"name": "Qatar",        "desc": "Qatar share of SG crude petroleum imports (SITC 333)."},
    "sg_imp_share_sitc_333_kw": {"name": "Kuwait",       "desc": "Kuwait share of SG crude petroleum imports (SITC 333)."},
    "sg_imp_share_sitc_333_iq": {"name": "Iraq",         "desc": "Iraq share of SG crude petroleum imports (SITC 333)."},
    "sg_imp_share_sitc_333_om": {"name": "Oman",         "desc": "Oman share of SG crude petroleum imports (SITC 333)."},

    "sg_imp_share_sitc_334_ae": {"name": "UAE",          "desc": "UAE share of SG refined petroleum product imports (SITC 334)."},
    "sg_imp_share_sitc_334_sa": {"name": "Saudi Arabia", "desc": "Saudi Arabia share of SG refined petroleum product imports (SITC 334)."},
    "sg_imp_share_sitc_334_qa": {"name": "Qatar",        "desc": "Qatar share of SG refined petroleum product imports (SITC 334)."},
    "sg_imp_share_sitc_334_kw": {"name": "Kuwait",       "desc": "Kuwait share of SG refined petroleum product imports (SITC 334)."},
    "sg_imp_share_sitc_334_iq": {"name": "Iraq",         "desc": "Iraq share of SG refined petroleum product imports (SITC 334)."},
    "sg_imp_share_sitc_334_om": {"name": "Oman",         "desc": "Oman share of SG refined petroleum product imports (SITC 334)."},

    "sg_imp_share_sitc_343_ae": {"name": "UAE",          "desc": "UAE share of SG natural gas imports (SITC 343)."},
    "sg_imp_share_sitc_343_sa": {"name": "Saudi Arabia", "desc": "Saudi Arabia share of SG natural gas imports (SITC 343)."},
    "sg_imp_share_sitc_343_qa": {"name": "Qatar",        "desc": "Qatar share of SG natural gas imports (SITC 343)."},
    "sg_imp_share_sitc_343_kw": {"name": "Kuwait",       "desc": "Kuwait share of SG natural gas imports (SITC 343)."},
    "sg_imp_share_sitc_343_iq": {"name": "Iraq",         "desc": "Iraq share of SG natural gas imports (SITC 343)."},
    "sg_imp_share_sitc_343_om": {"name": "Oman",         "desc": "Oman share of SG natural gas imports (SITC 343)."},

    # SITC 3346043 (refined petroleum sub-product) — share series
    "sg_imp_share_sitc_3346043_ae": {"name": "UAE",          "desc": "UAE share of SG naphtha imports."},
    "sg_imp_share_sitc_3346043_sa": {"name": "Saudi Arabia", "desc": "Saudi Arabia share of SG naphtha imports."},
    "sg_imp_share_sitc_3346043_qa": {"name": "Qatar",        "desc": "Qatar share of SG naphtha imports."},
    "sg_imp_share_sitc_3346043_kw": {"name": "Kuwait",       "desc": "Kuwait share of SG naphtha imports."},
    "sg_imp_share_sitc_3346043_iq": {"name": "Iraq",         "desc": "Iraq share of SG naphtha imports."},
    "sg_imp_share_sitc_3346043_om": {"name": "Oman",         "desc": "Oman share of SG naphtha imports."},

    # SITC 3431000 (natural gas sub-product) — share series
    "sg_imp_share_sitc_3431000_ae": {"name": "UAE",          "desc": "UAE share of SG LNG imports."},
    "sg_imp_share_sitc_3431000_sa": {"name": "Saudi Arabia", "desc": "Saudi Arabia share of SG LNG imports."},
    "sg_imp_share_sitc_3431000_qa": {"name": "Qatar",        "desc": "Qatar share of SG LNG imports."},
    "sg_imp_share_sitc_3431000_kw": {"name": "Kuwait",       "desc": "Kuwait share of SG LNG imports."},
    "sg_imp_share_sitc_3431000_iq": {"name": "Iraq",         "desc": "Iraq share of SG LNG imports."},
    "sg_imp_share_sitc_3431000_om": {"name": "Oman",         "desc": "Oman share of SG LNG imports."},

    # "Others" residual (annual share — bars stack to 100%)
    "sg_imp_share_sitc_3_others":         {"name": "Others", "desc": "Non-ME-spotlight partners' aggregate share of SG mineral fuel imports (SITC 3)."},
    "sg_imp_share_sitc_333_others":       {"name": "Others", "desc": "Non-ME-spotlight partners' share of SG crude petroleum imports (SITC 333)."},
    "sg_imp_share_sitc_334_others":       {"name": "Others", "desc": "Non-ME-spotlight partners' share of SG refined-product imports (SITC 334)."},
    "sg_imp_share_sitc_343_others":       {"name": "Others", "desc": "Non-ME-spotlight partners' share of SG natural gas imports (SITC 343)."},
    "sg_imp_share_sitc_3346043_others":   {"name": "Others", "desc": "Non-ME-spotlight partners' share of SG naphtha imports."},
    "sg_imp_share_sitc_3431000_others":   {"name": "Others", "desc": "Non-ME-spotlight partners' share of SG LNG imports."},

    # Per-partner monthly levels — used by the right (stacked monthly) chart
    # of each SITC row. SITC 3 (mineral fuels total)
    "sg_imp_monthly_sitc_3_ae":           {"name": "UAE",          "desc": "Monthly SG mineral fuel imports from UAE."},
    "sg_imp_monthly_sitc_3_sa":           {"name": "Saudi Arabia", "desc": "Monthly SG mineral fuel imports from Saudi Arabia."},
    "sg_imp_monthly_sitc_3_qa":           {"name": "Qatar",        "desc": "Monthly SG mineral fuel imports from Qatar."},
    "sg_imp_monthly_sitc_3_kw":           {"name": "Kuwait",       "desc": "Monthly SG mineral fuel imports from Kuwait."},
    "sg_imp_monthly_sitc_3_iq":           {"name": "Iraq",         "desc": "Monthly SG mineral fuel imports from Iraq."},
    "sg_imp_monthly_sitc_3_om":           {"name": "Oman",         "desc": "Monthly SG mineral fuel imports from Oman."},
    "sg_imp_monthly_sitc_3_others":       {"name": "Others",       "desc": "Monthly SG mineral fuel imports from non-ME partners."},

    # SITC 333 (crude petroleum) — monthly per partner + Others
    "sg_imp_monthly_sitc_333_ae":         {"name": "UAE",          "desc": "Monthly SG crude petroleum imports from UAE."},
    "sg_imp_monthly_sitc_333_sa":         {"name": "Saudi Arabia", "desc": "Monthly SG crude petroleum imports from Saudi Arabia."},
    "sg_imp_monthly_sitc_333_qa":         {"name": "Qatar",        "desc": "Monthly SG crude petroleum imports from Qatar."},
    "sg_imp_monthly_sitc_333_kw":         {"name": "Kuwait",       "desc": "Monthly SG crude petroleum imports from Kuwait."},
    "sg_imp_monthly_sitc_333_iq":         {"name": "Iraq",         "desc": "Monthly SG crude petroleum imports from Iraq."},
    "sg_imp_monthly_sitc_333_om":         {"name": "Oman",         "desc": "Monthly SG crude petroleum imports from Oman."},
    "sg_imp_monthly_sitc_333_others":     {"name": "Others",       "desc": "Monthly SG crude petroleum imports from non-ME partners."},

    # SITC 334 (refined petroleum) — monthly per partner + Others
    "sg_imp_monthly_sitc_334_ae":         {"name": "UAE",          "desc": "Monthly SG refined petroleum imports from UAE."},
    "sg_imp_monthly_sitc_334_sa":         {"name": "Saudi Arabia", "desc": "Monthly SG refined petroleum imports from Saudi Arabia."},
    "sg_imp_monthly_sitc_334_qa":         {"name": "Qatar",        "desc": "Monthly SG refined petroleum imports from Qatar."},
    "sg_imp_monthly_sitc_334_kw":         {"name": "Kuwait",       "desc": "Monthly SG refined petroleum imports from Kuwait."},
    "sg_imp_monthly_sitc_334_iq":         {"name": "Iraq",         "desc": "Monthly SG refined petroleum imports from Iraq."},
    "sg_imp_monthly_sitc_334_om":         {"name": "Oman",         "desc": "Monthly SG refined petroleum imports from Oman."},
    "sg_imp_monthly_sitc_334_others":     {"name": "Others",       "desc": "Monthly SG refined petroleum imports from non-ME partners."},

    # SITC 343 (natural gas) — monthly per partner + Others
    "sg_imp_monthly_sitc_343_ae":         {"name": "UAE",          "desc": "Monthly SG natural gas imports from UAE."},
    "sg_imp_monthly_sitc_343_sa":         {"name": "Saudi Arabia", "desc": "Monthly SG natural gas imports from Saudi Arabia."},
    "sg_imp_monthly_sitc_343_qa":         {"name": "Qatar",        "desc": "Monthly SG natural gas imports from Qatar."},
    "sg_imp_monthly_sitc_343_kw":         {"name": "Kuwait",       "desc": "Monthly SG natural gas imports from Kuwait."},
    "sg_imp_monthly_sitc_343_iq":         {"name": "Iraq",         "desc": "Monthly SG natural gas imports from Iraq."},
    "sg_imp_monthly_sitc_343_om":         {"name": "Oman",         "desc": "Monthly SG natural gas imports from Oman."},
    "sg_imp_monthly_sitc_343_others":     {"name": "Others",       "desc": "Monthly SG natural gas imports from non-ME partners."},

    # SITC 3346043 — monthly per partner + Others
    "sg_imp_monthly_sitc_3346043_ae":     {"name": "UAE",          "desc": "Monthly SG naphtha imports from UAE."},
    "sg_imp_monthly_sitc_3346043_sa":     {"name": "Saudi Arabia", "desc": "Monthly SG naphtha imports from Saudi Arabia."},
    "sg_imp_monthly_sitc_3346043_qa":     {"name": "Qatar",        "desc": "Monthly SG naphtha imports from Qatar."},
    "sg_imp_monthly_sitc_3346043_kw":     {"name": "Kuwait",       "desc": "Monthly SG naphtha imports from Kuwait."},
    "sg_imp_monthly_sitc_3346043_iq":     {"name": "Iraq",         "desc": "Monthly SG naphtha imports from Iraq."},
    "sg_imp_monthly_sitc_3346043_om":     {"name": "Oman",         "desc": "Monthly SG naphtha imports from Oman."},
    "sg_imp_monthly_sitc_3346043_others": {"name": "Others",       "desc": "Monthly SG naphtha imports from non-ME partners."},

    # SITC 3431000 — monthly per partner + Others
    "sg_imp_monthly_sitc_3431000_ae":     {"name": "UAE",          "desc": "Monthly SG LNG imports from UAE."},
    "sg_imp_monthly_sitc_3431000_sa":     {"name": "Saudi Arabia", "desc": "Monthly SG LNG imports from Saudi Arabia."},
    "sg_imp_monthly_sitc_3431000_qa":     {"name": "Qatar",        "desc": "Monthly SG LNG imports from Qatar."},
    "sg_imp_monthly_sitc_3431000_kw":     {"name": "Kuwait",       "desc": "Monthly SG LNG imports from Kuwait."},
    "sg_imp_monthly_sitc_3431000_iq":     {"name": "Iraq",         "desc": "Monthly SG LNG imports from Iraq."},
    "sg_imp_monthly_sitc_3431000_om":     {"name": "Oman",         "desc": "Monthly SG LNG imports from Oman."},
    "sg_imp_monthly_sitc_3431000_others": {"name": "Others",       "desc": "Monthly SG LNG imports from non-ME partners."},

    # Section 3: regional shares of SG industrial-chemical exports.
    # Friendly name = country (legend on stacked-bar chart).
    "sg_chem_export_share_cn": {"name": "China",       "desc": "China's share of SG industrial-chemical exports."},
    "sg_chem_export_share_in": {"name": "India",       "desc": "India's share of SG industrial-chemical exports."},
    "sg_chem_export_share_id": {"name": "Indonesia",   "desc": "Indonesia's share of SG industrial-chemical exports."},
    "sg_chem_export_share_jp": {"name": "Japan",       "desc": "Japan's share of SG industrial-chemical exports."},
    "sg_chem_export_share_my": {"name": "Malaysia",    "desc": "Malaysia's share of SG industrial-chemical exports."},
    "sg_chem_export_share_ph": {"name": "Philippines", "desc": "Philippines' share of SG industrial-chemical exports."},
    "sg_chem_export_share_kr": {"name": "South Korea", "desc": "South Korea's share of SG industrial-chemical exports."},
    "sg_chem_export_share_tw": {"name": "Taiwan",      "desc": "Taiwan's share of SG industrial-chemical exports."},
    "sg_chem_export_share_th": {"name": "Thailand",    "desc": "Thailand's share of SG industrial-chemical exports."},
    "sg_chem_export_share_vn": {"name": "Vietnam",     "desc": "Vietnam's share of SG industrial-chemical exports."},

    # Section 4: monthly chemical-export aggregates. Same naming convention
    # as Section 2 — short friendlies so the title de-dup catches them.
    "sg_chem_export_monthly_total":    {"name": "Total",             "desc": "Monthly SG industrial-chemical exports — total across all destinations."},
    "sg_chem_export_monthly_regional": {"name": "Regional aggregate","desc": "Monthly SG industrial-chemical exports — sum of 10 regional Asian economies."},

    # ════════════════════════════════════════════════════════════════════
    # SINGAPORE SHIPPING TAB — PortWatch shipping nowcast projections.
    # Every series gets friendly_name "Actual" or "Counterfactual (Primary)"
    # so each chart's legend pair is identical and the colors are uniform
    # across the whole tab (blue for actual, purple-dashed for CF — matching
    # the original shipping-nowcast dashboard's scheme). The flow type
    # (Total / Imports / Exports) lives in each subchart's subtitle, not
    # in the legend, so we don't have to repeat it.
    # ════════════════════════════════════════════════════════════════════
    "nowcast_sg_total_calls_actual":         {"name": "Actual",                   "desc": "Singapore total weekly port calls across all vessel types — actual count."},
    "nowcast_sg_total_calls_cf":             {"name": "Counterfactual (Primary)", "desc": "Singapore total weekly port calls — counterfactual estimate had the war not occurred."},

    # Tanker — calls + imports tonnage + exports tonnage
    "nowcast_sg_tanker_calls_actual":        {"name": "Actual",                   "desc": "Singapore weekly tanker port calls — actual count."},
    "nowcast_sg_tanker_calls_cf":            {"name": "Counterfactual (Primary)", "desc": "Singapore weekly tanker port calls — counterfactual."},
    # Note: the upstream nowcast pipeline emits tanker tonnage under the
    # un-suffixed key `country:singapore_<dir>_tonnage` (a quirk of
    # nowcast_pipeline.py:1826 — `label_suffix = "_tonnage" if vt_key == "tanker"`).
    # Confirmed: weekly mean of daily import_tanker sums × 7 matches raw CSV
    # sum within rounding. Numbers below ARE tanker-specific.
    "nowcast_sg_tanker_imp_tonnage_actual":  {"name": "Actual",                   "desc": "Singapore weekly inbound tanker tonnage — cargo unloaded."},
    "nowcast_sg_tanker_imp_tonnage_cf":      {"name": "Counterfactual (Primary)", "desc": "Singapore weekly inbound tanker tonnage — counterfactual."},
    "nowcast_sg_tanker_exp_tonnage_actual":  {"name": "Actual",                   "desc": "Singapore weekly outbound tanker tonnage — cargo loaded."},
    "nowcast_sg_tanker_exp_tonnage_cf":      {"name": "Counterfactual (Primary)", "desc": "Singapore weekly outbound tanker tonnage — counterfactual."},

    # Container — calls + imports tonnage + exports tonnage
    "nowcast_sg_container_calls_actual":     {"name": "Actual",                   "desc": "Singapore weekly container port calls — actual count."},
    "nowcast_sg_container_calls_cf":         {"name": "Counterfactual (Primary)", "desc": "Singapore weekly container port calls — counterfactual."},
    "nowcast_sg_container_imp_tonnage_actual":{"name":"Actual",                   "desc": "Singapore weekly inbound container tonnage — cargo unloaded."},
    "nowcast_sg_container_imp_tonnage_cf":   {"name": "Counterfactual (Primary)", "desc": "Singapore weekly inbound container tonnage — counterfactual."},
    "nowcast_sg_container_exp_tonnage_actual":{"name":"Actual",                   "desc": "Singapore weekly outbound container tonnage — cargo loaded."},
    "nowcast_sg_container_exp_tonnage_cf":   {"name": "Counterfactual (Primary)", "desc": "Singapore weekly outbound container tonnage — counterfactual."},

    "nowcast_malacca_total_actual":          {"name": "Actual",                   "desc": "Malacca Strait — total weekly vessel transits (all types) — actual."},
    "nowcast_malacca_total_cf":              {"name": "Counterfactual (Primary)", "desc": "Malacca Strait — total weekly vessel transits — counterfactual."},

    # ════════════════════════════════════════════════════════════════════
    # SINGAPORE FINANCIAL MARKETS TAB
    # ════════════════════════════════════════════════════════════════════
    # ────────────────────────────────────────────────────────────────────
    # Regional Financial Markets — yfinance / ADB / investing.com tickers.
    # Friendly names show up as the dataset legend label on each chart.
    # ────────────────────────────────────────────────────────────────────
    "JPY":           {"name": "JPY",          "desc": "Japanese yen vs USD (yfinance JPY=X)."},
    "CNY":           {"name": "CNY",          "desc": "Chinese yuan vs USD, onshore reference rate (yfinance CNY=X)."},

    # Indexed FX — rebased to 100 at 2026-01-01 so currencies with very
    # different magnitudes can share an axis. Higher value = weaker
    # local currency vs USD. The "indexed" framing is in the section/chart
    # title; legend just shows the currency code.
    "fx_indexed_idr": {"name": "Indonesian Rupiah",  "desc": "Indonesian Rupiah indexed to 100 on 2026-01-01."},
    "fx_indexed_myr": {"name": "Malaysian Ringgit",  "desc": "Malaysian Ringgit indexed to 100 on 2026-01-01."},
    "fx_indexed_php": {"name": "Philippine Peso",    "desc": "Philippine Peso indexed to 100 on 2026-01-01."},
    "fx_indexed_thb": {"name": "Thai Baht",          "desc": "Thai Baht indexed to 100 on 2026-01-01."},
    "fx_indexed_vnd": {"name": "Vietnamese Dong",    "desc": "Vietnamese Dong indexed to 100 on 2026-01-01."},
    "fx_indexed_jpy": {"name": "Japanese Yen",       "desc": "Japanese Yen indexed to 100 on 2026-01-01."},
    "fx_indexed_cny": {"name": "Chinese Yuan",       "desc": "Chinese Yuan indexed to 100 on 2026-01-01."},
    "VN_10Y":        {"name": "Vietnam 10Y",  "desc": "Vietnam 10-year sovereign bond yield (ADB AsianBondsOnline, % per annum)."},
    "COPPER":        {"name": "COMEX Copper", "desc": "COMEX copper futures, USD per pound (yfinance HG=F)."},
    "ALUMINUM":      {"name": "LME Aluminum", "desc": "LME aluminum futures, USD per tonne (Investing.com)."},
    "SHFE_NICKEL":   {"name": "SHFE Nickel",  "desc": "Shanghai Futures Exchange nickel futures, CNY per tonne (Investing.com)."},

    # ────────────────────────────────────────────────────────────────────
    # Singapore Financial Markets — Bloomberg-sourced gsheets series
    # (added 2026-04-30 from new "SG Financial Markets" tab).
    # ────────────────────────────────────────────────────────────────────
    "gsheets_s_pore_domestic_ib_avg_o_n":      {"name": "Domestic interbank overnight",  "desc": "Singapore domestic interbank average overnight rate (Rate, daily, Bloomberg)."},
    "gsheets_sgd_singapore_govt_bval_2y":      {"name": "BVAL 2Y",                 "desc": "Bloomberg Valuation 2-year SGS yield, % per annum, daily."},
    "gsheets_sgd_singapore_govt_bval_10y":     {"name": "BVAL 10Y",                "desc": "Bloomberg Valuation 10-year SGS yield, % per annum, daily."},
    "gsheets_nominal_effec_rt":                {"name": "NEER",                    "desc": "Singapore Nominal Effective Exchange Rate (trade-weighted index, daily, Bloomberg). MAS policy band reference."},
    "gsheets_singapore_real_effective_excha":  {"name": "REER",                    "desc": "Singapore Real Effective Exchange Rate (trade-weighted index deflated by relative CPI, daily, Bloomberg)."},
    "gsheets_us_dollar_singapore_dollar":      {"name": "USD/SGD spot",            "desc": "USD/SGD spot rate (price/base, daily, Bloomberg)."},
    "gsheets_singapore_dollar_1_mo":           {"name": "USD/SGD 1M forward",      "desc": "USD/SGD 1-month forward (price/base, daily, Bloomberg)."},
    "gsheets_singapore_dollar_3_mo":           {"name": "USD/SGD 3M forward",      "desc": "USD/SGD 3-month forward (price/base, daily, Bloomberg)."},
    "gsheets_usd_sgd_opt_vol_1m":              {"name": "USD/SGD 1M implied vol",  "desc": "USD/SGD 1-month option implied volatility, annualised %, daily (Bloomberg)."},
    "gsheets_usd_sgd_opt_vol_3m":              {"name": "USD/SGD 3M implied vol",  "desc": "USD/SGD 3-month option implied volatility, annualised %, daily (Bloomberg)."},
    "gsheets_straits_times_index_sti":         {"name": "STI",                     "desc": "Straits Times Index (30 SGX-listed blue-chip companies), daily, Bloomberg."},

    "financial_yield_2y":                    {"name": "MAS 2Y yield",            "desc": "Singapore Government Securities (SGS) 2-year benchmark yield, % per annum, daily (CEIC / MAS)."},
    "financial_yield_10y":                   {"name": "MAS 10Y yield",           "desc": "Singapore Government Securities (SGS) 10-year benchmark yield, % per annum, daily (CEIC / MAS)."},
    "financial_sora_3m":                     {"name": "SORA 3M compounded",      "desc": "Singapore Overnight Rate Average compounded over 3 months, % per annum, daily (CEIC / MAS)."},
    "financial_sgx_turnover":                {"name": "SGX daily turnover",      "desc": "SGX equity market daily turnover, millions of shares (CEIC / SGX)."},
    "financial_forex_turnover":              {"name": "Forex monthly turnover",  "desc": "Singapore FX market monthly turnover (all instruments, all currency pairs), SGD millions (CEIC / MAS)."},
}


# ════════════════════════════════════════════════════════════════════
# REGIONAL SHIPPING TAB — same 7 metrics × 9 countries.
# Programmatically generated to keep the friendly names + descriptions
# uniform with the Singapore tab. Each country gets 14 series IDs:
#   nowcast_<iso2>_total_calls_actual / _cf
#   nowcast_<iso2>_tanker_calls_actual / _cf
#   nowcast_<iso2>_tanker_imp_tonnage_actual / _cf
#   nowcast_<iso2>_tanker_exp_tonnage_actual / _cf
#   nowcast_<iso2>_container_calls_actual / _cf
#   nowcast_<iso2>_container_imp_tonnage_actual / _cf
#   nowcast_<iso2>_container_exp_tonnage_actual / _cf
# ════════════════════════════════════════════════════════════════════
_REGIONAL_SHIPPING = [
    ("cn", "China"),
    ("in", "India"),
    ("id", "Indonesia"),
    ("jp", "Japan"),
    ("kr", "South Korea"),
    ("my", "Malaysia"),
    ("ph", "Philippines"),
    ("th", "Thailand"),
    ("vn", "Vietnam"),
]
for _iso2, _country in _REGIONAL_SHIPPING:
    SERIES_DESCRIPTIONS[f"nowcast_{_iso2}_total_calls_actual"] = {
        "name": "Actual",
        "desc": f"{_country} total weekly port calls across all vessel types — actual count."}
    SERIES_DESCRIPTIONS[f"nowcast_{_iso2}_total_calls_cf"] = {
        "name": "Counterfactual (Primary)",
        "desc": f"{_country} total weekly port calls — counterfactual estimate had the war not occurred."}
    # Tanker
    SERIES_DESCRIPTIONS[f"nowcast_{_iso2}_tanker_calls_actual"] = {
        "name": "Actual",
        "desc": f"{_country} weekly tanker port calls — actual count."}
    SERIES_DESCRIPTIONS[f"nowcast_{_iso2}_tanker_calls_cf"] = {
        "name": "Counterfactual (Primary)",
        "desc": f"{_country} weekly tanker port calls — counterfactual."}
    SERIES_DESCRIPTIONS[f"nowcast_{_iso2}_tanker_imp_tonnage_actual"] = {
        "name": "Actual",
        "desc": f"{_country} weekly inbound tanker tonnage — cargo unloaded."}
    SERIES_DESCRIPTIONS[f"nowcast_{_iso2}_tanker_imp_tonnage_cf"] = {
        "name": "Counterfactual (Primary)",
        "desc": f"{_country} weekly inbound tanker tonnage — counterfactual."}
    SERIES_DESCRIPTIONS[f"nowcast_{_iso2}_tanker_exp_tonnage_actual"] = {
        "name": "Actual",
        "desc": f"{_country} weekly outbound tanker tonnage — cargo loaded."}
    SERIES_DESCRIPTIONS[f"nowcast_{_iso2}_tanker_exp_tonnage_cf"] = {
        "name": "Counterfactual (Primary)",
        "desc": f"{_country} weekly outbound tanker tonnage — counterfactual."}
    # Container
    SERIES_DESCRIPTIONS[f"nowcast_{_iso2}_container_calls_actual"] = {
        "name": "Actual",
        "desc": f"{_country} weekly container port calls — actual count."}
    SERIES_DESCRIPTIONS[f"nowcast_{_iso2}_container_calls_cf"] = {
        "name": "Counterfactual (Primary)",
        "desc": f"{_country} weekly container port calls — counterfactual."}
    SERIES_DESCRIPTIONS[f"nowcast_{_iso2}_container_imp_tonnage_actual"] = {
        "name": "Actual",
        "desc": f"{_country} weekly inbound container tonnage — cargo unloaded."}
    SERIES_DESCRIPTIONS[f"nowcast_{_iso2}_container_imp_tonnage_cf"] = {
        "name": "Counterfactual (Primary)",
        "desc": f"{_country} weekly inbound container tonnage — counterfactual."}
    SERIES_DESCRIPTIONS[f"nowcast_{_iso2}_container_exp_tonnage_actual"] = {
        "name": "Actual",
        "desc": f"{_country} weekly outbound container tonnage — cargo loaded."}
    SERIES_DESCRIPTIONS[f"nowcast_{_iso2}_container_exp_tonnage_cf"] = {
        "name": "Counterfactual (Primary)",
        "desc": f"{_country} weekly outbound container tonnage — counterfactual."}


def lookup(series_id: str, series_name: str = "") -> dict | None:
    """Look up a series's friendly name and description.

    Tries series_id first (most stable for short IDs like 'motorist_92'),
    then series_name as a fallback. series_name handles cases where the
    series_id is too long and got truncated to 64 chars in the DB.
    """
    if series_id in SERIES_DESCRIPTIONS:
        return SERIES_DESCRIPTIONS[series_id]
    if series_name:
        return SERIES_DESCRIPTIONS.get(series_name)
    return None


# ════════════════════════════════════════════════════════════════════
# Editorial titles for multi-series unit-split charts
# ════════════════════════════════════════════════════════════════════
# When auto-split-by-unit produces a multi-series chart, the renderer's
# default fallback title is "{node_label} — {unit}" (e.g.
# "LPG — USD/gallon"). That's ugly and uninformative. Map (node_id, unit)
# to an editorial title here to override the unit string with something
# descriptive that explains what the chart is actually showing.
#
# Single-series-after-split charts already use the series's friendly name
# from SERIES_DESCRIPTIONS — they don't need entries here.

NODE_UNIT_TITLES: dict[str, dict[str, str]] = {
    "diesel_petrol": {
        "USD/barrel": "Singapore gasoline",
    },
    "naphtha": {
        "USD/metric tonne": "Japan & NWE delivered",
    },
    "lpg": {
        "USD/gallon": "US (Mont Belvieu spot)",
        "USD/metric tonne": "Arab Gulf contract",
    },
    "sg_cpi": {
        "% YoY": "Annual",
        "% MoM": "Monthly",
    },
    # 2026-04-30: legacy "construction" unit-split removed — node now lives as
    # two separate dependency nodes (construction_demand on Activity tab,
    # construction_prices on Prices tab) so unit-split is no longer needed.
}


def lookup_unit_title(node_id: str, unit: str) -> str | None:
    """Editorial title to use in place of '{unit}' for multi-series unit-split
    charts. Returns None if no override is defined; renderer falls back to the
    bare unit string."""
    return NODE_UNIT_TITLES.get(node_id, {}).get(unit)
