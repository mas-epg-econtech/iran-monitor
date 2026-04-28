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
    "CPI All Items YoY": {
        "name": "Headline CPI YoY",
        "desc": "Year-on-year change in the Singapore Consumer Price Index — the broadest measure of consumer inflation.",
    },
    "CPI All Items MoM": {
        "name": "CPI MoM",
        "desc": "Month-on-month change in the Singapore Consumer Price Index.",
    },
    "MAS Core Inflation YoY": {
        "name": "MAS Core",
        "desc": "MAS measure of core inflation, excluding accommodation and private road transport — preferred policy gauge.",
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
    # NB: avoid "IPI" abbreviation here — it conflicts with Industrial Production
    # Index (ipi_petroleum etc.) which is the more common SG-context meaning of IPI.
    "Import Price Index (Oil)": {
        "name": "Import: Oil",
        "desc": "Oil-related component of the Import Price Index — cost of oil imports into Singapore.",
    },
    "Import Price Index (Non-oil)": {
        "name": "Import: Non-oil",
        "desc": "Non-oil component of the Import Price Index.",
    },
    "Import Price Index (Food & Live Animals)": {
        "name": "Import: Food",
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
