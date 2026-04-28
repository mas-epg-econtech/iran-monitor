"""
Inline SVG country flags for MAS EPG report cards.

Simplified geometric renderings — recognizable but not pixel-accurate. Each
function returns a self-contained SVG string sized to fill its container.
ASEAN uses a stylized rice-stalk emblem (the official ASEAN symbol).
"""

# Common SVG wrapper: 3:2 aspect, fills container via width/height = 100%.
def _svg(body: str, view_w: int = 60, view_h: int = 40) -> str:
    return (
        f'<svg viewBox="0 0 {view_w} {view_h}" xmlns="http://www.w3.org/2000/svg" '
        f'preserveAspectRatio="xMidYMid meet" '
        f'style="width:100%; height:100%; display:block;">'
        f'{body}'
        f'</svg>'
    )


def flag_philippines() -> str:
    body = (
        # Blue top half, red bottom half
        '<rect width="60" height="20" fill="#0038A8"/>'
        '<rect y="20" width="60" height="20" fill="#CE1126"/>'
        # White triangle on hoist side
        '<polygon points="0,0 0,40 23,20" fill="#FFFFFF"/>'
        # Sun (8-ray) in center of triangle
        '<g transform="translate(8,20)" fill="#FCD116">'
        '<circle r="3"/>'
        # 8 rays
        + ''.join(
            f'<rect x="-0.5" y="-7" width="1" height="3.5" '
            f'transform="rotate({i * 45})"/>'
            for i in range(8)
        )
        + '</g>'
        # 3 stars in triangle corners
        '<polygon points="2,3 2.5,4.2 3.7,4.2 2.7,4.9 3.1,6.1 2,5.4 0.9,6.1 1.3,4.9 0.3,4.2 1.5,4.2" fill="#FCD116"/>'
        '<polygon points="2,37 2.5,35.8 3.7,35.8 2.7,35.1 3.1,33.9 2,34.6 0.9,33.9 1.3,35.1 0.3,35.8 1.5,35.8" fill="#FCD116"/>'
        '<polygon points="20,20 20.5,21.2 21.7,21.2 20.7,21.9 21.1,23.1 20,22.4 18.9,23.1 19.3,21.9 18.3,21.2 19.5,21.2" fill="#FCD116"/>'
    )
    return _svg(body)


def flag_india() -> str:
    body = (
        # Three horizontal bands: saffron, white, green
        '<rect width="60" height="13.33" fill="#FF9933"/>'
        '<rect y="13.33" width="60" height="13.33" fill="#FFFFFF"/>'
        '<rect y="26.66" width="60" height="13.34" fill="#138808"/>'
        # Ashoka Chakra — 24-spoke wheel in centre of white band
        '<g transform="translate(30,20)" stroke="#000080" fill="none">'
        '<circle r="5.5" stroke-width="0.6"/>'
        '<circle r="1" fill="#000080"/>'
        # 24 spokes
        + ''.join(
            f'<line x1="0" y1="0" x2="0" y2="-5" stroke-width="0.3" '
            f'transform="rotate({i * 15})"/>'
            for i in range(24)
        )
        + '</g>'
    )
    return _svg(body)


def flag_japan() -> str:
    body = (
        # White background, red circle
        '<rect width="60" height="40" fill="#FFFFFF"/>'
        '<circle cx="30" cy="20" r="12" fill="#BC002D"/>'
    )
    return _svg(body)


def flag_korea() -> str:
    # South Korean Taegukgi: white bg, central taegeuk (red+blue), 4 corner trigrams
    body = (
        '<rect width="60" height="40" fill="#FFFFFF"/>'
        # Taegeuk circle: blue lower wave + red upper wave (simplified as half-circles)
        '<g transform="translate(30,20)">'
        # Outer circle outline
        '<circle r="9" fill="#FFFFFF"/>'
        # Top half = red, bottom half = blue, with the S-curve via two smaller circles
        '<path d="M -9,0 A 9,9 0 0 1 9,0 A 4.5,4.5 0 0 0 0,0 A 4.5,4.5 0 0 1 -9,0 Z" fill="#CD2E3A"/>'
        '<path d="M 9,0 A 9,9 0 0 1 -9,0 A 4.5,4.5 0 0 0 0,0 A 4.5,4.5 0 0 1 9,0 Z" fill="#0047A0"/>'
        '</g>'
        # Trigrams (simplified as 3 stacked bars in each corner)
        # Geon (top-left): three solid bars
        '<g transform="translate(8,8)" fill="#000000">'
        '<rect x="-4" y="-1.2" width="8" height="0.8"/>'
        '<rect x="-4" y="-0.4" width="8" height="0.8"/>'
        '<rect x="-4" y="0.4" width="8" height="0.8"/>'
        '</g>'
        # Ri (top-right): three bars, middle broken
        '<g transform="translate(52,8)" fill="#000000">'
        '<rect x="-4" y="-1.2" width="8" height="0.8"/>'
        '<rect x="-4" y="-0.4" width="3" height="0.8"/>'
        '<rect x="1" y="-0.4" width="3" height="0.8"/>'
        '<rect x="-4" y="0.4" width="8" height="0.8"/>'
        '</g>'
        # Gam (bottom-left): three bars, top+bottom broken
        '<g transform="translate(8,32)" fill="#000000">'
        '<rect x="-4" y="-1.2" width="3" height="0.8"/>'
        '<rect x="1" y="-1.2" width="3" height="0.8"/>'
        '<rect x="-4" y="-0.4" width="8" height="0.8"/>'
        '<rect x="-4" y="0.4" width="3" height="0.8"/>'
        '<rect x="1" y="0.4" width="3" height="0.8"/>'
        '</g>'
        # Gon (bottom-right): three bars all broken
        '<g transform="translate(52,32)" fill="#000000">'
        '<rect x="-4" y="-1.2" width="3" height="0.8"/>'
        '<rect x="1" y="-1.2" width="3" height="0.8"/>'
        '<rect x="-4" y="-0.4" width="3" height="0.8"/>'
        '<rect x="1" y="-0.4" width="3" height="0.8"/>'
        '<rect x="-4" y="0.4" width="3" height="0.8"/>'
        '<rect x="1" y="0.4" width="3" height="0.8"/>'
        '</g>'
    )
    return _svg(body)


def flag_taiwan() -> str:
    # Red field, blue canton (top-left quarter) with white 12-ray sun
    body = (
        '<rect width="60" height="40" fill="#FE0000"/>'
        '<rect width="30" height="20" fill="#000095"/>'
        # White sun: 12-rayed
        '<g transform="translate(15,10)">'
        + ''.join(
            f'<polygon points="0,-7 1.2,-2 -1.2,-2" fill="#FFFFFF" '
            f'transform="rotate({i * 30})"/>'
            for i in range(12)
        )
        + '<circle r="2.5" fill="#000095"/>'
        + '<circle r="1.8" fill="#FFFFFF"/>'
        + '</g>'
    )
    return _svg(body)


def flag_asean() -> str:
    # Stylised ASEAN emblem: blue circle, red ring, white inner circle, 10 yellow rice stalks
    body = (
        # Blue background
        '<rect width="60" height="40" fill="#003F87"/>'
        # White outer circle
        '<circle cx="30" cy="20" r="14" fill="#FFFFFF"/>'
        # Red ring (annulus via two circles)
        '<circle cx="30" cy="20" r="13" fill="none" stroke="#CD1126" stroke-width="2"/>'
        # 10 yellow rice stalks (simplified as radial lines)
        + '<g transform="translate(30,20)" stroke="#FCD116" stroke-width="2.2" stroke-linecap="round">'
        + ''.join(
            f'<line x1="0" y1="-2" x2="0" y2="-9" '
            f'transform="rotate({(i - 5) * 18})"/>'
            for i in range(10)
        )
        + '</g>'
    )
    return _svg(body)


# Map ISO/region code -> SVG renderer
FLAGS = {
    "PH": flag_philippines,
    "IN": flag_india,
    "JP": flag_japan,
    "KR": flag_korea,
    "TW": flag_taiwan,
    "ASEAN": flag_asean,
}


def get_flag(iso: str) -> str:
    """Return inline SVG for a given country/region ISO code, or a generic placeholder."""
    fn = FLAGS.get(iso)
    if fn:
        return fn()
    # Generic placeholder: grey box with ISO text
    return (
        f'<svg viewBox="0 0 60 40" xmlns="http://www.w3.org/2000/svg" '
        f'preserveAspectRatio="xMidYMid meet" '
        f'style="width:100%; height:100%; display:block;">'
        f'<rect width="60" height="40" fill="#3a4252"/>'
        f'<text x="30" y="24" fill="#c9d4e3" font-family="Inter, sans-serif" '
        f'font-size="11" text-anchor="middle">{iso}</text>'
        f'</svg>'
    )
