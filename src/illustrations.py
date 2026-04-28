"""
Hero SVG illustrations for the landing page nav cards.

Each function returns a self-contained SVG sized for use as a card hero image
(roughly 16:9 aspect, fills its container). Stylized, minimal, dark-theme
compatible. Uses the dashboard accent palette (gold/teal/blue).
"""

# Common palette
GOLD = "#f0d08a"
GOLD_DIM = "#c29a51"
TEAL = "#60a5fa"
TEAL_DIM = "#3b82c4"
DARK = "#0a1623"
EMERALD = "#34d399"
SLATE = "#3a4252"

_SVG_OPEN = (
    '<svg viewBox="0 0 320 160" xmlns="http://www.w3.org/2000/svg" '
    'preserveAspectRatio="xMidYMid meet" '
    'style="width:100%; height:100%; display:block;">'
)
_SVG_CLOSE = '</svg>'


def hero_global_shocks() -> str:
    """Clean globe with the 5 maritime chokepoints marked; Hormuz highlighted with a pulse."""
    body = (
        '<defs>'
        '<radialGradient id="g_bg" cx="50%" cy="50%" r="70%">'
        f'<stop offset="0%" stop-color="{TEAL}" stop-opacity="0.16"/>'
        '<stop offset="100%" stop-color="#000" stop-opacity="0"/>'
        '</radialGradient>'
        # Globe surface gradient — simulates a 3D sphere with light source upper-left
        '<radialGradient id="g_globe" cx="35%" cy="30%" r="75%">'
        f'<stop offset="0%" stop-color="{TEAL}" stop-opacity="0.55"/>'
        f'<stop offset="60%" stop-color="{TEAL_DIM}" stop-opacity="0.30"/>'
        f'<stop offset="100%" stop-color="{TEAL_DIM}" stop-opacity="0.12"/>'
        '</radialGradient>'
        '</defs>'
        '<rect width="320" height="160" fill="url(#g_bg)"/>'
        # Globe — centered, larger
        '<g transform="translate(160 80)">'
        f'<circle r="62" fill="url(#g_globe)" stroke="{TEAL}" stroke-width="1.2" stroke-opacity="0.6"/>'
        # Just one equator line + one meridian for subtle depth
        f'<ellipse rx="62" ry="18" fill="none" stroke="{TEAL}" stroke-width="0.6" stroke-opacity="0.35"/>'
        f'<ellipse rx="20" ry="62" fill="none" stroke="{TEAL}" stroke-width="0.6" stroke-opacity="0.35"/>'
        # Chokepoint markers — gold dots at approximate world positions on the visible hemisphere.
        # Order: Suez, Bab el-Mandeb, Hormuz (highlighted), Cape, Malacca.
        # Suez (north, slightly east of center)
        f'<circle cx="14" cy="-22" r="2.4" fill="{GOLD}" fill-opacity="0.85"/>'
        # Bab el-Mandeb (closer to center-east, just south of equator)
        f'<circle cx="20" cy="6" r="2.4" fill="{GOLD}" fill-opacity="0.85"/>'
        # Cape of Good Hope (south, near pole)
        f'<circle cx="6" cy="48" r="2.4" fill="{GOLD}" fill-opacity="0.85"/>'
        # Malacca (far east, just south of equator)
        f'<circle cx="48" cy="14" r="2.4" fill="{GOLD}" fill-opacity="0.85"/>'
        # Hormuz — highlighted with pulse rings (the headline crisis location)
        f'<circle cx="32" cy="-8" r="4" fill="{GOLD}"/>'
        f'<circle cx="32" cy="-8" r="9" fill="none" stroke="{GOLD}" stroke-width="1.2" stroke-opacity="0.55"/>'
        f'<circle cx="32" cy="-8" r="14" fill="none" stroke="{GOLD}" stroke-width="0.8" stroke-opacity="0.25"/>'
        # Hormuz label
        f'<text x="38" y="-7" fill="{GOLD}" font-family="Inter, sans-serif" font-size="8" font-weight="600">Hormuz</text>'
        '</g>'
    )
    return _SVG_OPEN + body + _SVG_CLOSE


def hero_singapore() -> str:
    """Marina Bay-inspired skyline silhouette with sunset gradient."""
    body = (
        # Sunset gradient background
        '<defs>'
        '<linearGradient id="s_sky" x1="0%" y1="0%" x2="0%" y2="100%">'
        f'<stop offset="0%" stop-color="{DARK}" stop-opacity="0"/>'
        f'<stop offset="60%" stop-color="{GOLD}" stop-opacity="0.18"/>'
        f'<stop offset="100%" stop-color="{GOLD}" stop-opacity="0.05"/>'
        '</linearGradient>'
        '<linearGradient id="s_water" x1="0%" y1="0%" x2="0%" y2="100%">'
        f'<stop offset="0%" stop-color="{TEAL}" stop-opacity="0.25"/>'
        f'<stop offset="100%" stop-color="{TEAL_DIM}" stop-opacity="0.08"/>'
        '</linearGradient>'
        '</defs>'
        '<rect width="320" height="160" fill="url(#s_sky)"/>'
        # Sun
        f'<circle cx="240" cy="58" r="14" fill="{GOLD}" fill-opacity="0.7"/>'
        f'<circle cx="240" cy="58" r="22" fill="{GOLD}" fill-opacity="0.18"/>'
        # Water surface
        '<rect x="0" y="124" width="320" height="36" fill="url(#s_water)"/>'
        # Water reflection lines
        f'<line x1="20" y1="135" x2="80" y2="135" stroke="{TEAL}" stroke-width="0.6" stroke-opacity="0.4"/>'
        f'<line x1="60" y1="143" x2="180" y2="143" stroke="{TEAL}" stroke-width="0.6" stroke-opacity="0.3"/>'
        f'<line x1="200" y1="138" x2="280" y2="138" stroke="{TEAL}" stroke-width="0.6" stroke-opacity="0.4"/>'
        f'<line x1="100" y1="151" x2="220" y2="151" stroke="{TEAL}" stroke-width="0.6" stroke-opacity="0.25"/>'
        # Marina Bay Sands — three towers with sky park on top
        '<g transform="translate(110 60)">'
        # Tower 1
        f'<polygon points="0,64 0,12 14,0 14,64" fill="{GOLD_DIM}" fill-opacity="0.85"/>'
        # Tower 2
        f'<polygon points="32,64 32,12 46,0 46,64" fill="{GOLD_DIM}" fill-opacity="0.95"/>'
        # Tower 3
        f'<polygon points="64,64 64,12 78,0 78,64" fill="{GOLD_DIM}" fill-opacity="0.85"/>'
        # Sky park (the curved roof connecting the three)
        f'<path d="M -2 0 Q 38 -10 80 0 L 80 -4 Q 38 -14 -2 -4 Z" fill="{GOLD}"/>'
        '</g>'
        # Smaller skyscrapers on left (CBD)
        f'<rect x="20" y="80" width="14" height="44" fill="{SLATE}" fill-opacity="0.85"/>'
        f'<rect x="36" y="72" width="12" height="52" fill="{SLATE}" fill-opacity="0.9"/>'
        f'<rect x="50" y="86" width="16" height="38" fill="{SLATE}" fill-opacity="0.85"/>'
        f'<rect x="68" y="78" width="13" height="46" fill="{SLATE}" fill-opacity="0.92"/>'
        f'<rect x="83" y="92" width="10" height="32" fill="{SLATE}" fill-opacity="0.8"/>'
        # Right side: container terminal (port) silhouette
        f'<rect x="200" y="106" width="20" height="18" fill="{SLATE}" fill-opacity="0.9"/>'
        # Crane
        f'<line x1="218" y1="80" x2="218" y2="124" stroke="{SLATE}" stroke-width="2" stroke-opacity="0.85"/>'
        f'<line x1="208" y1="80" x2="232" y2="80" stroke="{SLATE}" stroke-width="1.5" stroke-opacity="0.85"/>'
        # Container stack on dock
        f'<rect x="244" y="116" width="14" height="8" fill="{GOLD}" fill-opacity="0.7"/>'
        f'<rect x="260" y="116" width="14" height="8" fill="{TEAL}" fill-opacity="0.7"/>'
        f'<rect x="276" y="116" width="14" height="8" fill="{GOLD_DIM}" fill-opacity="0.7"/>'
        f'<rect x="252" y="108" width="14" height="8" fill="{TEAL_DIM}" fill-opacity="0.7"/>'
        f'<rect x="268" y="108" width="14" height="8" fill="{GOLD}" fill-opacity="0.7"/>'
    )
    return _SVG_OPEN + body + _SVG_CLOSE


def hero_regional_map() -> str:
    """Original literal-map version (kept for reference; not used by default)."""
    LAND_FILL = "rgba(96, 165, 250, 0.22)"   # soft teal, flat
    LAND_STROKE = "rgba(96, 165, 250, 0.85)" # crisper outline

    body = (
        '<defs>'
        '<linearGradient id="r_bg" x1="0%" y1="0%" x2="100%" y2="100%">'
        f'<stop offset="0%" stop-color="{TEAL}" stop-opacity="0.06"/>'
        f'<stop offset="100%" stop-color="{TEAL_DIM}" stop-opacity="0.03"/>'
        '</linearGradient>'
        '</defs>'
        '<rect width="320" height="160" fill="url(#r_bg)"/>'

        # ═══ Asian mainland — one continuous coastline path ═══
        # Drawn clockwise from western India, around the southern tip, up the
        # east coast through Bangladesh, down through Indochina/Malaysia, up the
        # east coast of Vietnam/China, around to NE China, then across the top
        # back to the start. Cubic Bezier curves for smooth coastlines.
        f'<path d="'
        # West coast of India — Mumbai bulge then taper to Cochin
        'M 50 70 '
        'C 48 80, 48 92, 56 108 '
        'C 60 118, 64 128, 70 130 '
        # Southern tip of India (Cape Comorin)
        'C 74 130, 76 124, 76 118 '
        # East coast of India — gentle curve up through Chennai to the Sundarbans
        'C 80 108, 84 96, 86 84 '
        # Bangladesh / NE India / Myanmar — dip slightly south then east
        'C 92 80, 100 78, 110 80 '
        'C 116 82, 122 86, 126 92 '
        # Myanmar coast going south through the Andaman Sea
        'C 130 100, 132 110, 134 120 '
        # Thailand / Malay peninsula tapering toward Singapore
        'C 134 128, 132 138, 138 142 '
        'C 142 144, 146 138, 146 130 '
        # Up the east coast of Malaysia/Vietnam
        'C 148 118, 152 108, 158 100 '
        'C 164 94, 172 90, 182 88 '
        # South China coast through Guangzhou, Shanghai
        'C 196 86, 210 82, 220 74 '
        # NE China up toward Shandong / Beijing
        'C 226 66, 230 56, 232 46 '
        # Top of China — sweep west through Mongolia border
        'C 218 38, 196 32, 170 30 '
        'C 142 30, 116 34, 92 42 '
        # Western boundary back down through Pakistan area
        'C 70 50, 56 60, 50 70 '
        'Z" '
        f'fill="{LAND_FILL}" stroke="{LAND_STROKE}" stroke-width="0.6"/>'

        # ═══ Sri Lanka (small teardrop south of India) ═══
        f'<path d="M 80 124 C 84 124, 86 130, 84 134 C 80 136, 78 132, 78 128 Z" '
        f'fill="{LAND_FILL}" stroke="{LAND_STROKE}" stroke-width="0.5"/>'

        # ═══ Korean peninsula (attached visually to mainland) ═══
        f'<path d="M 234 46 C 240 50, 242 60, 240 70 C 238 76, 232 78, 228 72 C 226 62, 228 50, 234 46 Z" '
        f'fill="{LAND_FILL}" stroke="{LAND_STROKE}" stroke-width="0.6"/>'

        # ═══ Japan — three islands forming the characteristic arc ═══
        # Hokkaido (north)
        f'<path d="M 268 24 C 276 26, 282 32, 280 40 C 276 44, 270 44, 266 40 C 262 34, 264 26, 268 24 Z" '
        f'fill="{LAND_FILL}" stroke="{LAND_STROKE}" stroke-width="0.5"/>'
        # Honshu (main island, curved)
        f'<path d="M 256 40 C 266 42, 274 50, 278 60 C 280 68, 274 76, 268 74 C 260 70, 254 60, 252 50 C 252 44, 254 40, 256 40 Z" '
        f'fill="{LAND_FILL}" stroke="{LAND_STROKE}" stroke-width="0.5"/>'
        # Kyushu (south)
        f'<path d="M 264 80 C 272 82, 278 88, 276 94 C 272 98, 266 96, 262 92 C 260 88, 260 82, 264 80 Z" '
        f'fill="{LAND_FILL}" stroke="{LAND_STROKE}" stroke-width="0.5"/>'

        # ═══ Taiwan ═══
        f'<path d="M 218 90 C 222 92, 224 98, 222 104 C 220 106, 216 104, 215 100 C 214 95, 215 91, 218 90 Z" '
        f'fill="{LAND_FILL}" stroke="{LAND_STROKE}" stroke-width="0.5"/>'

        # ═══ Philippine archipelago — cleaner organic shapes ═══
        # Luzon (largest, north)
        f'<path d="M 188 94 C 194 96, 198 102, 198 110 C 196 114, 190 114, 186 110 C 184 104, 184 98, 188 94 Z" '
        f'fill="{LAND_FILL}" stroke="{LAND_STROKE}" stroke-width="0.5"/>'
        # Visayas (small clusters in middle)
        f'<circle cx="194" cy="118" r="2.2" fill="{LAND_FILL}" stroke="{LAND_STROKE}" stroke-width="0.4"/>'
        f'<circle cx="200" cy="120" r="1.6" fill="{LAND_FILL}" stroke="{LAND_STROKE}" stroke-width="0.4"/>'
        # Mindanao (south)
        f'<path d="M 196 124 C 204 126, 208 132, 206 138 C 202 140, 196 138, 194 134 C 192 130, 193 126, 196 124 Z" '
        f'fill="{LAND_FILL}" stroke="{LAND_STROKE}" stroke-width="0.5"/>'

        # ═══ Indonesian archipelago — Sumatra, Java, Borneo, Sulawesi ═══
        # Sumatra (long, curved NW-SE)
        f'<path d="M 132 132 C 144 134, 156 138, 166 142 C 168 144, 168 146, 164 146 C 152 144, 140 140, 128 136 C 128 134, 130 132, 132 132 Z" '
        f'fill="{LAND_FILL}" stroke="{LAND_STROKE}" stroke-width="0.5"/>'
        # Java (long horizontal strip south of Sumatra)
        f'<path d="M 156 150 C 172 150, 188 152, 196 152 C 198 154, 196 156, 188 156 C 174 156, 160 154, 154 152 C 154 151, 155 150, 156 150 Z" '
        f'fill="{LAND_FILL}" stroke="{LAND_STROKE}" stroke-width="0.5"/>'
        # Borneo (large blob in centre)
        f'<path d="M 170 124 C 184 124, 192 132, 192 140 C 190 146, 180 148, 172 144 C 166 140, 166 130, 170 124 Z" '
        f'fill="{LAND_FILL}" stroke="{LAND_STROKE}" stroke-width="0.5"/>'
        # Sulawesi (K-shaped island east)
        f'<path d="M 200 130 C 206 130, 210 134, 208 140 C 206 144, 202 144, 200 140 C 198 138, 196 134, 200 130 Z" '
        f'fill="{LAND_FILL}" stroke="{LAND_STROKE}" stroke-width="0.5"/>'

        # ═══ Country markers (6 PDF countries) — gold dots with code labels ═══
        '<g>'
        # India — placed inland, central peninsula
        f'<circle cx="64" cy="98" r="3" fill="{GOLD}"/>'
        f'<text x="48" y="102" fill="{GOLD}" font-family="Inter, sans-serif" font-size="8" font-weight="600">IN</text>'
        # ASEAN — anchored on Indonesia mainland (Borneo region)
        f'<circle cx="180" cy="138" r="3" fill="{GOLD}"/>'
        f'<text x="184" y="142" fill="{GOLD}" font-family="Inter, sans-serif" font-size="8" font-weight="600">ASEAN</text>'
        # Philippines — on Luzon
        f'<circle cx="192" cy="106" r="3" fill="{GOLD}"/>'
        f'<text x="198" y="110" fill="{GOLD}" font-family="Inter, sans-serif" font-size="8" font-weight="600">PH</text>'
        # Korea
        f'<circle cx="235" cy="60" r="3" fill="{GOLD}"/>'
        f'<text x="216" y="48" fill="{GOLD}" font-family="Inter, sans-serif" font-size="8" font-weight="600">KR</text>'
        # Taiwan
        f'<circle cx="219" cy="98" r="3" fill="{GOLD}"/>'
        f'<text x="225" y="102" fill="{GOLD}" font-family="Inter, sans-serif" font-size="8" font-weight="600">TW</text>'
        # Japan — on Honshu
        f'<circle cx="266" cy="56" r="3" fill="{GOLD}"/>'
        f'<text x="272" y="60" fill="{GOLD}" font-family="Inter, sans-serif" font-size="8" font-weight="600">JP</text>'
        '</g>'
    )
    return _SVG_OPEN + body + _SVG_CLOSE


def hero_regional_chart() -> str:
    """Multi-line chart aesthetic (kept for reference; not used by default).

    Six smooth lines representing the regional indicators tracked on the
    Regional dashboard, each labelled with a country code on the right.
    """
    # Six countries each get one line of a distinct accent color.
    # Colors chosen to be visible on dark background without being garish.
    LINES = [
        # (country_code, color, y_start, y_end, dip_y, peak_y, opacity)
        ("ASEAN", "#34d399", 38,  46,  44,  30,  0.85),  # emerald — top line
        ("JP",    "#f0d08a", 60,  56,  68,  50,  0.85),  # gold
        ("KR",    "#60a5fa", 78,  82,  72,  88,  0.85),  # blue
        ("TW",    "#fbbf24", 96,  92, 102,  86,  0.85),  # amber
        ("IN",    "#f87171",116, 110,124, 104,  0.85),   # rose
        ("PH",    "#22d3ee",134, 132,142, 124,  0.85),   # cyan
    ]

    # Background + subtle grid
    body = [
        '<defs>',
        '<linearGradient id="r_bg" x1="0%" y1="0%" x2="100%" y2="100%">',
        f'<stop offset="0%" stop-color="{TEAL}" stop-opacity="0.08"/>',
        f'<stop offset="100%" stop-color="{DARK}" stop-opacity="0.0"/>',
        '</linearGradient>',
        # Glow filter for line endpoints
        '<filter id="glow" x="-50%" y="-50%" width="200%" height="200%">',
        '<feGaussianBlur stdDeviation="1.6" result="b"/>',
        '<feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>',
        '</filter>',
        '</defs>',
        '<rect width="320" height="160" fill="url(#r_bg)"/>',

        # ── Subtle horizontal grid lines ──
        '<g stroke="rgba(224,230,239,0.06)" stroke-width="0.5">',
        *[f'<line x1="20" y1="{y}" x2="280" y2="{y}"/>' for y in (40, 70, 100, 130)],
        '</g>',
        # Y-axis baseline (left)
        f'<line x1="20" y1="20" x2="20" y2="148" stroke="rgba(224,230,239,0.18)" stroke-width="0.7"/>',
        # X-axis baseline (bottom)
        f'<line x1="20" y1="148" x2="280" y2="148" stroke="rgba(224,230,239,0.18)" stroke-width="0.7"/>',
    ]

    # Draw each line as a smooth wavy path.
    # Path goes from x=22 → x=276 with cubic Beziers creating gentle ups and downs.
    for code, color, y_start, y_end, dip, peak, alpha in LINES:
        # Construct a smooth path with 4 control segments
        path = (
            f'M 22 {y_start} '
            f'C 70 {dip}, 110 {peak}, 150 {y_start - 4} '
            f'C 190 {y_start + 6}, 220 {peak - 2}, 250 {y_end - 2} '
            f'C 264 {y_end - 4}, 270 {y_end}, 276 {y_end}'
        )
        # The line itself (with subtle glow via filter on the endpoint dot only)
        body.append(
            f'<path d="{path}" fill="none" stroke="{color}" stroke-width="1.6" '
            f'stroke-opacity="{alpha}" stroke-linecap="round" stroke-linejoin="round"/>'
        )
        # Endpoint dot (slightly glowing)
        body.append(
            f'<circle cx="276" cy="{y_end}" r="2.6" fill="{color}" filter="url(#glow)"/>'
        )
        # Country code label to the right of the endpoint
        body.append(
            f'<text x="284" y="{y_end + 3}" fill="{color}" font-family="Inter, sans-serif" '
            f'font-size="9" font-weight="600">{code}</text>'
        )

    return _SVG_OPEN + "".join(body) + _SVG_CLOSE


def hero_regional_hub() -> str:
    """Hub-and-spoke variant (kept for reference; not used by default).

    Hexagonal arrangement around a glowing central hub. Each country node is a
    colored dot with a country-code label; spokes connect each node to the hub;
    subtle dashed lines outline the hexagon to suggest network interconnection.
    """
    HUB_X, HUB_Y = 160, 82

    # Country nodes — (code, color, x, y, label_dx, label_dy, text_anchor)
    # Six vertices of a horizontally-stretched hexagon around the hub.
    NODES = [
        ("IN",    "#f87171",   72,  82,  -10,   4, "end"),     # left (India)
        ("ASEAN", "#34d399",  118, 130,    0,  16, "middle"),  # lower-left
        ("PH",    "#60a5fa",  202, 130,    0,  16, "middle"),  # lower-right
        ("TW",    "#fbbf24",  248,  82,   10,   4, "start"),   # right (Taiwan)
        ("JP",    "#f0d08a",  202,  34,    0, -10, "middle"),  # upper-right
        ("KR",    "#22d3ee",  118,  34,    0, -10, "middle"),  # upper-left
    ]

    body = [
        '<defs>',
        # Soft radial backdrop, gold fading outward into transparency
        '<radialGradient id="r_hub_bg" cx="50%" cy="50%" r="60%">',
        f'<stop offset="0%" stop-color="{GOLD}" stop-opacity="0.10"/>',
        f'<stop offset="55%" stop-color="{TEAL}" stop-opacity="0.06"/>',
        '<stop offset="100%" stop-color="#000" stop-opacity="0"/>',
        '</radialGradient>',
        # Glow filter for the central hub
        '<filter id="hub_glow" x="-100%" y="-100%" width="300%" height="300%">',
        '<feGaussianBlur stdDeviation="2.4" result="b"/>',
        '<feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>',
        '</filter>',
        '</defs>',
        '<rect width="320" height="160" fill="url(#r_hub_bg)"/>',
    ]

    # Hexagon-edge connections (subtle dashed lines between adjacent nodes,
    # giving a "network" feel rather than a pure star)
    n = len(NODES)
    for i in range(n):
        n1 = NODES[i]
        n2 = NODES[(i + 1) % n]
        body.append(
            f'<line x1="{n1[2]}" y1="{n1[3]}" x2="{n2[2]}" y2="{n2[3]}" '
            f'stroke="rgba(240,208,138,0.18)" stroke-width="0.5" stroke-dasharray="2 3"/>'
        )

    # Spokes from hub to each node
    for code, color, x, y, *_ in NODES:
        body.append(
            f'<line x1="{HUB_X}" y1="{HUB_Y}" x2="{x}" y2="{y}" '
            f'stroke="{color}" stroke-width="0.9" stroke-opacity="0.45"/>'
        )

    # Central hub — layered glowing concentric circles (halo effect)
    body.append(f'<circle cx="{HUB_X}" cy="{HUB_Y}" r="20" fill="{GOLD}" fill-opacity="0.05"/>')
    body.append(f'<circle cx="{HUB_X}" cy="{HUB_Y}" r="12" fill="{GOLD}" fill-opacity="0.14"/>')
    body.append(f'<circle cx="{HUB_X}" cy="{HUB_Y}" r="6.5" fill="{GOLD}" filter="url(#hub_glow)"/>')

    # Country nodes — colored dots with halos and labels
    for code, color, x, y, dx, dy, anchor in NODES:
        body.append(f'<circle cx="{x}" cy="{y}" r="9" fill="{color}" fill-opacity="0.12"/>')
        body.append(f'<circle cx="{x}" cy="{y}" r="4.2" fill="{color}"/>')
        body.append(
            f'<text x="{x + dx}" y="{y + dy}" fill="{color}" '
            f'font-family="Inter, sans-serif" font-size="9.5" font-weight="600" '
            f'text-anchor="{anchor}">{code}</text>'
        )

    return _SVG_OPEN + "".join(body) + _SVG_CLOSE


def hero_regional() -> str:
    """Real-geography Asia map — built from world-atlas/countries-110m TopoJSON
    (Natural Earth Admin 0 1:110m). Uses an equirectangular projection with the
    bounding box LNG 60–150 / LAT -12 to 55, matching what's defined in
    src/asia_paths.py.
    """
    from .asia_paths import ASIA_PATHS

    # Same projection used in src/asia_paths.py — keep these in sync.
    SVG_W, SVG_H = 320, 160
    LNG_MIN, LNG_MAX = 60, 150
    LAT_MIN, LAT_MAX = -12, 55

    def project(lng: float, lat: float) -> tuple[float, float]:
        x = (lng - LNG_MIN) / (LNG_MAX - LNG_MIN) * SVG_W
        y = (1 - (lat - LAT_MIN) / (LAT_MAX - LAT_MIN)) * SVG_H
        return x, y

    LAND_FILL = "rgba(96, 165, 250, 0.20)"   # subtle teal
    LAND_STROKE = "rgba(96, 165, 250, 0.85)" # crisper outline

    body = [
        '<defs>',
        '<linearGradient id="r_geo_bg" x1="0%" y1="0%" x2="100%" y2="100%">',
        f'<stop offset="0%" stop-color="{TEAL}" stop-opacity="0.06"/>',
        f'<stop offset="100%" stop-color="{TEAL_DIM}" stop-opacity="0.03"/>',
        '</linearGradient>',
        '</defs>',
        '<rect width="320" height="160" fill="url(#r_geo_bg)"/>',
    ]

    # Render each country path with a single fill + thin outline. No internal
    # country borders to worry about because each country is its own closed path.
    for iso, info in ASIA_PATHS.items():
        body.append(
            f'<path d="{info["d"]}" fill="{LAND_FILL}" stroke="{LAND_STROKE}" '
            f'stroke-width="0.5" stroke-linejoin="round"/>'
        )

    # Country markers for the report countries (ASEAN broken out into individual
    # Malaysia, Indonesia, Thailand). Centroids picked at well-known capitals or
    # central points; label dx/dy/anchor tuned so dots and labels don't collide.
    markers = [
        # iso, lng,  lat,  label, dx,  dy, anchor
        ("IN",  78,    22,  "IN",  -5,  -4, "end"),    # India (central)
        ("TH", 101,    14,  "TH",  -6,  -3, "end"),    # Thailand (Bangkok)
        ("MY", 102,     4,  "MY",   6,  -3, "start"),  # Malaysia (peninsular)
        ("ID", 110,    -3,  "ID",   6,   3, "start"),  # Indonesia (central)
        ("PH", 122,    13,  "PH",   6,  -3, "start"),  # Philippines (Manila)
        ("KR", 128,    37,  "KR",   6,  -3, "start"),  # Korea (Seoul)
        ("TW", 121,  23.5,  "TW",  -6,  -3, "end"),    # Taiwan (Taipei)
        ("JP", 138,    36,  "JP",   6,  -3, "start"),  # Japan (Tokyo)
    ]
    for iso, lng, lat, label, dx, dy, anchor in markers:
        x, y = project(lng, lat)
        body.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="6" fill="{GOLD}" fill-opacity="0.18"/>'
        )
        body.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.2" fill="{GOLD}"/>'
        )
        body.append(
            f'<text x="{x + dx:.1f}" y="{y + dy:.1f}" fill="{GOLD}" '
            f'font-family="Inter, sans-serif" font-size="9" font-weight="600" '
            f'text-anchor="{anchor}" '
            f'paint-order="stroke" stroke="rgba(10,22,35,0.9)" stroke-width="2.5">'
            f'{label}</text>'
        )

    return _SVG_OPEN + "".join(body) + _SVG_CLOSE


# Map slug -> hero illustration
HEROES = {
    "global_shocks": hero_global_shocks,
    "singapore":     hero_singapore,
    "regional":      hero_regional,
}


def get_hero(slug: str) -> str:
    fn = HEROES.get(slug)
    return fn() if fn else ""
