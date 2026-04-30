"""SingStat country/market name → display label + ISO-2 mapping.

SingStat publishes verbose, all-caps country labels (e.g., "KOREA, REP OF",
"UNITED ARAB EMIRATES", "VIET NAM"). This module maps those to:
  - `display`: a clean, human-readable name for chart labels
  - `iso2`:    ISO-3166 alpha-2 code, used to look up flag SVGs

The dict only needs to cover countries that actually appear in our trade data
and that we want to show with a flag/clean label. Unmapped countries get
their raw SingStat name passed through (no flag, capitalised name).

Coverage priorities (in order):
  1. Iran-crisis Middle East spotlight (suppliers): IR, SA, AE, KW, IQ, QA, OM, IL, BH
  2. 10 regional Asia (chemical export buyers):     CN, IN, ID, JP, MY, PH, KR, TW, TH, VN
  3. Other top SG trading partners by import value
"""
from __future__ import annotations


# Map: SingStat raw name (uppercase, exact) → {display, iso2}
# Lookup is case-insensitive; we normalise on the lookup side.
SINGSTAT_COUNTRY_MAP: dict[str, dict[str, str]] = {

    # ── Middle East — Iran-crisis spotlight ──
    "IRAN":                  {"display": "Iran",                  "iso2": "IR"},
    "SAUDI ARABIA":          {"display": "Saudi Arabia",          "iso2": "SA"},
    "UNITED ARAB EMIRATES":  {"display": "UAE",                   "iso2": "AE"},
    "KUWAIT":                {"display": "Kuwait",                "iso2": "KW"},
    "IRAQ":                  {"display": "Iraq",                  "iso2": "IQ"},
    "QATAR":                 {"display": "Qatar",                 "iso2": "QA"},
    "OMAN":                  {"display": "Oman",                  "iso2": "OM"},
    "ISRAEL":                {"display": "Israel",                "iso2": "IL"},
    "BAHRAIN":               {"display": "Bahrain",               "iso2": "BH"},
    "YEMEN":                 {"display": "Yemen",                 "iso2": "YE"},
    "JORDAN":                {"display": "Jordan",                "iso2": "JO"},
    "LEBANON":               {"display": "Lebanon",               "iso2": "LB"},

    # ── Regional Asia — chemicals export spotlight ──
    "CHINA":                 {"display": "China",                 "iso2": "CN"},
    "INDIA":                 {"display": "India",                 "iso2": "IN"},
    "INDONESIA":             {"display": "Indonesia",             "iso2": "ID"},
    "JAPAN":                 {"display": "Japan",                 "iso2": "JP"},
    "MALAYSIA":              {"display": "Malaysia",              "iso2": "MY"},
    "PHILIPPINES":           {"display": "Philippines",           "iso2": "PH"},
    "KOREA, REP OF":         {"display": "South Korea",           "iso2": "KR"},
    "TAIWAN":                {"display": "Taiwan",                "iso2": "TW"},
    "THAILAND":              {"display": "Thailand",              "iso2": "TH"},
    "VIET NAM":              {"display": "Vietnam",               "iso2": "VN"},

    # ── Other ASEAN ──
    "BRUNEI":                {"display": "Brunei",                "iso2": "BN"},
    "CAMBODIA":              {"display": "Cambodia",              "iso2": "KH"},
    "MYANMAR":               {"display": "Myanmar",               "iso2": "MM"},
    "TIMOR-LESTE":           {"display": "Timor-Leste",           "iso2": "TL"},

    # ── Other top SG trading partners by import value ──
    "BRAZIL":                {"display": "Brazil",                "iso2": "BR"},
    "UNITED STATES":         {"display": "United States",         "iso2": "US"},
    "RUSSIA":                {"display": "Russia",                "iso2": "RU"},
    "AUSTRALIA":             {"display": "Australia",             "iso2": "AU"},
    "NIGERIA":               {"display": "Nigeria",               "iso2": "NG"},
    "ANGOLA":                {"display": "Angola",                "iso2": "AO"},
    "SOUTH SUDAN":           {"display": "South Sudan",           "iso2": "SS"},
    "SUDAN":                 {"display": "Sudan",                 "iso2": "SD"},
    "LIBYA":                 {"display": "Libya",                 "iso2": "LY"},
    "EGYPT":                 {"display": "Egypt",                 "iso2": "EG"},
    "ALGERIA":               {"display": "Algeria",               "iso2": "DZ"},
    "KAZAKHSTAN":            {"display": "Kazakhstan",            "iso2": "KZ"},
    "AZERBAIJAN":            {"display": "Azerbaijan",            "iso2": "AZ"},
    "TURKMENISTAN":          {"display": "Turkmenistan",          "iso2": "TM"},
    "PAKISTAN":              {"display": "Pakistan",              "iso2": "PK"},
    "BANGLADESH":            {"display": "Bangladesh",            "iso2": "BD"},
    "SRI LANKA":             {"display": "Sri Lanka",             "iso2": "LK"},
    "HONG KONG":             {"display": "Hong Kong",             "iso2": "HK"},
    "NEW ZEALAND":           {"display": "New Zealand",           "iso2": "NZ"},
    "PAPUA NEW GUINEA":      {"display": "Papua New Guinea",      "iso2": "PG"},
    "TÜRKIYE":               {"display": "Türkiye",               "iso2": "TR"},
    "TURKEY":                {"display": "Türkiye",               "iso2": "TR"},  # alias

    # ── Europe (frequent partners) ──
    "UNITED KINGDOM":        {"display": "United Kingdom",        "iso2": "GB"},
    "GERMANY":               {"display": "Germany",               "iso2": "DE"},
    "FRANCE":                {"display": "France",                "iso2": "FR"},
    "ITALY":                 {"display": "Italy",                 "iso2": "IT"},
    "NETHERLANDS":           {"display": "Netherlands",           "iso2": "NL"},
    "BELGIUM":               {"display": "Belgium",               "iso2": "BE"},
    "SPAIN":                 {"display": "Spain",                 "iso2": "ES"},
    "PORTUGAL":              {"display": "Portugal",              "iso2": "PT"},
    "DENMARK":               {"display": "Denmark",               "iso2": "DK"},
    "SWEDEN":                {"display": "Sweden",                "iso2": "SE"},
    "NORWAY":                {"display": "Norway",                "iso2": "NO"},
    "FINLAND":               {"display": "Finland",               "iso2": "FI"},
    "ESTONIA":               {"display": "Estonia",               "iso2": "EE"},
    "LATVIA":                {"display": "Latvia",                "iso2": "LV"},
    "LITHUANIA":             {"display": "Lithuania",             "iso2": "LT"},
    "POLAND":                {"display": "Poland",                "iso2": "PL"},
    "CZECH REP":             {"display": "Czechia",               "iso2": "CZ"},
    "SLOVAKIA":              {"display": "Slovakia",              "iso2": "SK"},
    "HUNGARY":               {"display": "Hungary",               "iso2": "HU"},
    "AUSTRIA":               {"display": "Austria",               "iso2": "AT"},
    "SWITZERLAND":           {"display": "Switzerland",           "iso2": "CH"},
    "IRELAND":               {"display": "Ireland",               "iso2": "IE"},
    "ROMANIA":               {"display": "Romania",               "iso2": "RO"},
    "BULGARIA":              {"display": "Bulgaria",              "iso2": "BG"},
    "GREECE":                {"display": "Greece",                "iso2": "GR"},
    "SLOVENIA":              {"display": "Slovenia",              "iso2": "SI"},
    "CROATIA":               {"display": "Croatia",               "iso2": "HR"},
    "SERBIA":                {"display": "Serbia",                "iso2": "RS"},
    "UKRAINE":               {"display": "Ukraine",               "iso2": "UA"},
    "GEORGIA":               {"display": "Georgia",               "iso2": "GE"},
    "MALTA":                 {"display": "Malta",                 "iso2": "MT"},
    "CYPRUS":                {"display": "Cyprus",                "iso2": "CY"},

    # ── Africa (long tail) ──
    "MOZAMBIQUE":            {"display": "Mozambique",            "iso2": "MZ"},
    "GHANA":                 {"display": "Ghana",                 "iso2": "GH"},
    "SOUTH AFRICA":          {"display": "South Africa",          "iso2": "ZA"},
    "MOROCCO":               {"display": "Morocco",               "iso2": "MA"},
    "TUNISIA":               {"display": "Tunisia",               "iso2": "TN"},
    "TANZANIA":              {"display": "Tanzania",              "iso2": "TZ"},
    "KENYA":                 {"display": "Kenya",                 "iso2": "KE"},
    "MADAGASCAR":            {"display": "Madagascar",            "iso2": "MG"},
    "MAURITIUS":             {"display": "Mauritius",             "iso2": "MU"},
    "CONGO":                 {"display": "Congo",                 "iso2": "CG"},
    "CONGO, DEM REP OF":     {"display": "DR Congo",              "iso2": "CD"},
    "COTE D'IVOIRE":         {"display": "Côte d'Ivoire",         "iso2": "CI"},
    "SENEGAL":               {"display": "Senegal",               "iso2": "SN"},
    "GUINEA":                {"display": "Guinea",                "iso2": "GN"},
    "EQUATORIAL GUINEA":     {"display": "Equatorial Guinea",     "iso2": "GQ"},
    "NIGER":                 {"display": "Niger",                 "iso2": "NE"},
    "BENIN":                 {"display": "Benin",                 "iso2": "BJ"},
    "TOGO":                  {"display": "Togo",                  "iso2": "TG"},
    "CAMEROON":              {"display": "Cameroon",              "iso2": "CM"},
    "LIBERIA":               {"display": "Liberia",               "iso2": "LR"},
    "DJIBOUTI":              {"display": "Djibouti",              "iso2": "DJ"},
    "SOMALIA":               {"display": "Somalia",               "iso2": "SO"},
    "ZAMBIA":                {"display": "Zambia",                "iso2": "ZM"},
    "NAMIBIA":               {"display": "Namibia",               "iso2": "NA"},

    # ── Americas (long tail) ──
    "CANADA":                {"display": "Canada",                "iso2": "CA"},
    "MEXICO":                {"display": "Mexico",                "iso2": "MX"},
    "ARGENTINA":             {"display": "Argentina",             "iso2": "AR"},
    "CHILE":                 {"display": "Chile",                 "iso2": "CL"},
    "PERU":                  {"display": "Peru",                  "iso2": "PE"},
    "COLOMBIA":              {"display": "Colombia",              "iso2": "CO"},
    "URUGUAY":               {"display": "Uruguay",               "iso2": "UY"},
    "BOLIVIA":               {"display": "Bolivia",               "iso2": "BO"},
    "GUYANA":                {"display": "Guyana",                "iso2": "GY"},
    "ECUADOR":               {"display": "Ecuador",               "iso2": "EC"},
    "TRINIDAD AND TOBAGO":   {"display": "Trinidad & Tobago",     "iso2": "TT"},
    "JAMAICA":               {"display": "Jamaica",               "iso2": "JM"},
    "CUBA":                  {"display": "Cuba",                  "iso2": "CU"},
    "BAHAMAS":               {"display": "Bahamas",               "iso2": "BS"},
    "PANAMA":                {"display": "Panama",                "iso2": "PA"},
    "COSTA RICA":            {"display": "Costa Rica",            "iso2": "CR"},
    "GUATEMALA":             {"display": "Guatemala",             "iso2": "GT"},
    "HONDURAS":              {"display": "Honduras",              "iso2": "HN"},

    # ── Pacific ──
    "FIJI":                  {"display": "Fiji",                  "iso2": "FJ"},
    "SOLOMON ISLANDS":       {"display": "Solomon Islands",       "iso2": "SB"},
    "NEW CALEDONIA":         {"display": "New Caledonia",         "iso2": "NC"},
    "GUAM":                  {"display": "Guam",                  "iso2": "GU"},

    # ── Oddballs / territories ──
    "GREENLAND":             {"display": "Greenland",             "iso2": "GL"},
    "GIBRALTAR":             {"display": "Gibraltar",             "iso2": "GI"},
    "ISLE OF MAN":           {"display": "Isle of Man",           "iso2": "IM"},
    "MALDIVES":              {"display": "Maldives",              "iso2": "MV"},
    "BRITISH INDIAN OCEAN TERRITORY": {"display": "BIOT",         "iso2": "IO"},
    "KYRGYZSTAN":            {"display": "Kyrgyzstan",            "iso2": "KG"},
}


def lookup(singstat_name: str) -> dict | None:
    """Look up a SingStat country label. Case-insensitive, whitespace-tolerant.

    Returns a dict {display, iso2} on hit, or None on miss (caller falls back
    to the raw name with title-casing).
    """
    if not singstat_name:
        return None
    key = singstat_name.strip().upper()
    return SINGSTAT_COUNTRY_MAP.get(key)


def display_name(singstat_name: str) -> str:
    """Best-effort display name. Falls back to title-case if unmapped."""
    hit = lookup(singstat_name)
    if hit:
        return hit["display"]
    # Title-case fallback for "MOZAMBIQUE" → "Mozambique"
    return (singstat_name or "").strip().title() or singstat_name


def iso2(singstat_name: str) -> str | None:
    """ISO-2 code or None if unmapped."""
    hit = lookup(singstat_name)
    return hit["iso2"] if hit else None
