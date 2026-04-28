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
        "name": "DSPI: Oil",
        "desc": "Oil-related component of the Domestic Supply Price Index — captures upstream cost pressure on oil-based goods supplied within Singapore.",
    },
    "Domestic Supply Price Index (Non-oil)": {
        "name": "DSPI: Non-oil",
        "desc": "Non-oil component of the Domestic Supply Price Index — pressure on non-oil goods supplied within Singapore.",
    },

    # ── SG Import Prices ─────────────────────────────────────────────────
    # IPI here = Import Price Index. The chart card's description spells this
    # out and notes the distinction from IIP (Industrial Production Index),
    # so using "IPI:" in the legend is unambiguous in context.
    "Import Price Index (Oil)": {
        "name": "IPI: Oil",
        "desc": "Oil-related component of the Import Price Index — cost of oil imports into Singapore.",
    },
    "Import Price Index (Non-oil)": {
        "name": "IPI: Non-oil",
        "desc": "Non-oil component of the Import Price Index.",
    },
    "Import Price Index (Food & Live Animals)": {
        "name": "IPI: Food",
        "desc": "Food and live animals component of the Import Price Index — cost of food imports.",
    },

    # ── SG Export Prices ─────────────────────────────────────────────────
    "Export Price Index (Oil)": {
        "name": "EPI: Oil",
        "desc": "Oil-related component of the Export Price Index — sales prices of Singapore's refined-product exports.",
    },
    "Export Price Index (Non-oil)": {
        "name": "EPI: Non-oil",
        "desc": "Non-oil component of the Export Price Index.",
    },

    # ── SG Producer Prices ───────────────────────────────────────────────
    "Manufactured Producers Price Index (Oil)": {
        "name": "MPPI: Oil",
        "desc": "Oil-related component of the Manufactured Producers Price Index — factory-gate prices for petroleum products.",
    },
    "Manufactured Producers Price Index (Non-oil)": {
        "name": "MPPI: Non-oil",
        "desc": "Non-oil component of the Manufactured Producers Price Index.",
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
    "IIP: Chemicals Cluster": {
        "name": "IIP",
        "desc": "Index of Industrial Production for the broader chemicals cluster.",
    },
    "IIP: Specialty Chemicals": {
        "name": "IIP: Specialty",
        "desc": "Index of Industrial Production for specialty chemicals — high-margin specialty inputs (paints, coatings, adhesives, etc.).",
    },

    # ── Wholesale ────────────────────────────────────────────────────────
    "Wholesale Trade Index: Ship Chandlers & Bunkering": {
        "name": "Bunkering",
        "desc": "Wholesale Trade Index for ship chandlers and bunkering — directly tied to marine fuel volumes at Singapore.",
    },
    "Wholesale Trade Index: Total excl Petroleum": {
        "name": "Total ex-petroleum",
        "desc": "Wholesale Trade Index excluding petroleum — broader wholesale activity.",
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
    "Construction Materials Demand: Ready-mixed Concrete": {
        "name": "Ready-mixed concrete - demand",
        "desc": "Monthly ready-mixed concrete demand (volume).",
    },
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
    "Construction Materials Price: Ready-mixed Concrete": {
        "name": "Ready-mixed concrete - prices",
        "desc": "Monthly ready-mixed concrete price (SGD/cubic metre).",
    },

    # ── Real estate ──────────────────────────────────────────────────────
    "Property Price Index: Private Residential (URA)": {
        "name": "Private property PPI",
        "desc": "URA Private Residential Property Price Index — quarterly benchmark for non-HDB housing prices.",
    },
    "Residential Property Transactions: Deals (URA)": {
        "name": "Property deals",
        "desc": "URA monthly count of private residential property transactions — proxy for buyer activity.",
    },

    # ── Food & beverage ──────────────────────────────────────────────────
    "Food and Beverage Services Value (2025=100)": {
        "name": "F&B services index",
        "desc": "F&B services value index — captures sales volume in restaurants, cafes, and food caterers.",
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
    # REGIONAL — Industrial Production
    # Each country uses its own base year (noted in unit) so the auto-split-by-
    # unit renderer will produce one chart per country. Friendly name = country.
    # ════════════════════════════════════════════════════════════════════
    "regional_ipi_cn": {"name": "China",       "desc": "China industrial production index (NBS) — output across mining, manufacturing, and utilities."},
    "regional_ipi_in": {"name": "India",       "desc": "India index of industrial production (MoSPI) — output across mining, manufacturing, and electricity."},
    "regional_ipi_id": {"name": "Indonesia",   "desc": "Indonesia large & medium manufacturing production index (BPS)."},
    "regional_ipi_jp": {"name": "Japan",       "desc": "Japan mining & manufacturing production index (METI)."},
    "regional_ipi_my": {"name": "Malaysia",    "desc": "Malaysia industrial production index (DOSM) — mining, manufacturing, and electricity."},
    "regional_ipi_ph": {"name": "Philippines", "desc": "Philippines volume of production index for manufacturing (PSA)."},
    "regional_ipi_kr": {"name": "South Korea", "desc": "South Korea all-industry production index (KOSTAT) — broad activity gauge across industry, services, and construction."},
    "regional_ipi_tw": {"name": "Taiwan",      "desc": "Taiwan industrial production index (MOEA) — mining, manufacturing, and utilities."},
    "regional_ipi_th": {"name": "Thailand",    "desc": "Thailand value-added manufacturing production index (OIE)."},
    "regional_ipi_vn": {"name": "Vietnam",     "desc": "Vietnam industrial production index (GSO) — mining, manufacturing, electricity, and water."},
}


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
    "construction": {
        "SGD/Ton": "Material prices",
        "Ton th": "Material demand",
    },
}


def lookup_unit_title(node_id: str, unit: str) -> str | None:
    """Editorial title to use in place of '{unit}' for multi-series unit-split
    charts. Returns None if no override is defined; renderer falls back to the
    bare unit string."""
    return NODE_UNIT_TITLES.get(node_id, {}).get(unit)
