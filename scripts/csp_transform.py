"""
Iran Monitor — CSP-compliant HTML transform for Airbase deployment.

Airbase enforces a Content Security Policy that bans inline <script>,
inline event handlers (onclick / onchange), and CDN-hosted JavaScript.
This module post-transforms the regular GitHub-Pages-style HTML emitted
by `build_iran_monitor.py` into a CSP-compliant variant.

Transformations applied:

  1. Strip the single inline <script>...</script> block from the HTML.
     Split its contents into:
        - A "static" section (helpers, event delegation) → dashboard.js,
          identical for every page.
        - A "data" section (CHART_CONFIGS, NO_DEFAULT_ZOOM) → per-page
          chart-configs-<page>.js.
     Replace the inline block in the HTML with external <script src="...">
     tags loading both files.

  2. Replace CDN <script src="https://..."> tags for Chart.js + Luxon +
     Chart.js plugins with <script src="vendor/<name>"> referencing the
     local copies under public/vendor/.

  3. Replace inline event handlers with data-* attributes that the
     event-delegation code in dashboard.js wires up at runtime:
        onclick="closeAccessWarning()"     → data-action="close-access-warning"
        onclick="setDateRange('war')"      → data-action="set-date-range" data-range="war"
        onclick="switchTab(this, 'X')"     → data-action="switch-tab" data-tab="X"
        onclick="toggleChartZoom(this)"    → data-action="toggle-chart-zoom"
        onclick="pdfCardClick(event,...)"  → data-action="pdf-card-click"
        onchange="switchView(this)"        → data-action="switch-view"
        onchange="switchCountryPanel(this)" → data-action="switch-country-panel"

Public API:

    csp_transform_page(html: str, page_slug: str) -> tuple[str, str, str]
        Returns (transformed_html, dashboard_js, chart_configs_js).
        The dashboard_js is identical for every page (same content) — the
        caller can write it once.
"""
from __future__ import annotations

import re


# ---------------------------------------------------------------------------
# CDN → vendor mapping
# ---------------------------------------------------------------------------
_CDN_VENDOR_MAP = {
    "https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js":
        "vendor/chart.umd.min.js",
    "https://cdn.jsdelivr.net/npm/luxon@3.4.4/build/global/luxon.min.js":
        "vendor/luxon.min.js",
    "https://cdn.jsdelivr.net/npm/chartjs-adapter-luxon@1.3.1/dist/chartjs-adapter-luxon.umd.min.js":
        "vendor/chartjs-adapter-luxon.umd.min.js",
    "https://cdn.jsdelivr.net/npm/chartjs-plugin-annotation@3.0.1/dist/chartjs-plugin-annotation.min.js":
        "vendor/chartjs-plugin-annotation.min.js",
}

# Google Fonts is loaded via <link> not <script>, so it's not blocked by
# script-src. style-src/font-src may need separate handling if Airbase's
# CSP is stricter — leave for now and adjust if browser console complains.


# ---------------------------------------------------------------------------
# Inline-handler → data-attribute transforms
# ---------------------------------------------------------------------------
# Each tuple: (regex pattern matching the onclick/onchange attribute,
#              replacement string with data-* attributes).
# Order matters — more-specific patterns first.
_HANDLER_REPLACEMENTS = [
    # closeAccessWarning() — modal close
    (re.compile(r'onclick="closeAccessWarning\(\)"'),
     'data-action="close-access-warning"'),

    # setDateRange('X') — war / 1y / all date-range buttons
    (re.compile(r"""onclick="setDateRange\('([^']+)'\)" """, re.VERBOSE),
     r'data-action="set-date-range" data-range="\1"'),

    # switchTab(this, 'X') — tab buttons
    (re.compile(r"""onclick="switchTab\(this,\s*'([^']+)'\)" """, re.VERBOSE),
     r'data-action="switch-tab" data-tab="\1"'),

    # toggleChartZoom(this) — per-chart zoom toggle
    (re.compile(r'onclick="toggleChartZoom\(this\)"'),
     'data-action="toggle-chart-zoom"'),

    # pdfCardClick(event, this.href) — PDF cards
    (re.compile(r'onclick="pdfCardClick\(event,\s*this\.href\)"'),
     'data-action="pdf-card-click"'),

    # switchView(this) — view-selector dropdowns
    (re.compile(r'onchange="switchView\(this\)"'),
     'data-action="switch-view"'),

    # switchCountryPanel(this) — country-selector dropdowns
    (re.compile(r'onchange="switchCountryPanel\(this\)"'),
     'data-action="switch-country-panel"'),
]


# ---------------------------------------------------------------------------
# Event-delegation code injected into dashboard.js
# ---------------------------------------------------------------------------
# Wires the data-action attributes to the existing handler functions, which
# are still defined in the inline-script-extracted dashboard.js code.
_EVENT_DELEGATION_JS = """
// ── CSP-compliant event delegation ──
// In CSP mode the HTML carries no inline `onclick`/`onchange` attributes;
// elements are tagged with `data-action` (plus auxiliary `data-*` for any
// extra parameters), and this delegation block routes events to the same
// handler functions that existed in the inline-handler version.
document.addEventListener('click', function (e) {
  const el = e.target.closest('[data-action]');
  if (!el) return;
  const action = el.dataset.action;
  switch (action) {
    case 'close-access-warning':
      if (typeof closeAccessWarning === 'function') closeAccessWarning();
      break;
    case 'set-date-range':
      if (typeof setDateRange === 'function') setDateRange(el.dataset.range);
      break;
    case 'switch-tab':
      if (typeof switchTab === 'function') switchTab(el, el.dataset.tab);
      break;
    case 'toggle-chart-zoom':
      if (typeof toggleChartZoom === 'function') toggleChartZoom(el);
      break;
    case 'pdf-card-click':
      if (typeof pdfCardClick === 'function') pdfCardClick(e, el.href);
      break;
  }
});
document.addEventListener('change', function (e) {
  const el = e.target.closest('[data-action]');
  if (!el) return;
  const action = el.dataset.action;
  switch (action) {
    case 'switch-view':
      if (typeof switchView === 'function') switchView(el);
      break;
    case 'switch-country-panel':
      if (typeof switchCountryPanel === 'function') switchCountryPanel(el);
      break;
  }
});
"""


# ---------------------------------------------------------------------------
# Inline-script extraction
# ---------------------------------------------------------------------------
# The build emits exactly one `<script>` block (without src attribute) just
# before the closing </body>. We split its contents into:
#   - A data prefix:  the lines defining `const CHART_CONFIGS = {...};` and
#                     `const NO_DEFAULT_ZOOM = new Set([...]);`. These vary
#                     per page → chart-configs-<page>.js.
#   - The remainder:  helpers + DOMContentLoaded handler. Identical across
#                     pages → dashboard.js.
_INLINE_SCRIPT_RE = re.compile(
    r"<script>\s*(.*?)\s*</script>",
    re.DOTALL,
)
_DATA_LINES_RE = re.compile(
    r"^(\s*const CHART_CONFIGS\s*=.*?;\s*\n"
    r"\s*//[^\n]*\n"             # comment line above NO_DEFAULT_ZOOM
    r"\s*//[^\n]*\n"             # second comment line
    r"\s*const NO_DEFAULT_ZOOM\s*=.*?;\s*\n)",
    re.MULTILINE | re.DOTALL,
)


def _split_inline_script(script_body: str) -> tuple[str, str]:
    """Split the inline script's body into (per-page data, shared helpers).

    The data portion is the two const declarations near the top of the
    DOMContentLoaded block; everything else is reusable across pages.
    Returns (data_js, helpers_js)."""
    m = _DATA_LINES_RE.search(script_body)
    if not m:
        # Fallback — couldn't parse. Treat the whole thing as helpers and
        # let the caller render an empty data file. This will still work
        # in-browser as long as dashboard.js doesn't reference the symbols
        # before they're defined.
        return "", script_body

    data_block = m.group(1).strip()
    helpers_block = (script_body[: m.start()] + script_body[m.end():]).strip()
    return data_block, helpers_block


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def csp_transform_page(html: str, page_slug: str) -> tuple[str, str, str]:
    """Transform one HTML page into its CSP-compliant variant.

    Returns:
        transformed_html — HTML with inline handlers/scripts replaced.
        dashboard_js     — shared JS file content (same for every page).
        chart_configs_js — per-page CHART_CONFIGS + NO_DEFAULT_ZOOM.
    """
    # 1. CDN → vendor — replace src URLs in <script src="..."> tags.
    out = html
    for cdn_url, vendor_path in _CDN_VENDOR_MAP.items():
        out = out.replace(cdn_url, vendor_path)

    # 2. Inline handlers → data-* attributes.
    for pattern, replacement in _HANDLER_REPLACEMENTS:
        out = pattern.sub(replacement, out)

    # 3. Extract the inline <script> block.
    m = _INLINE_SCRIPT_RE.search(out)
    if not m:
        # No inline script in this page — nothing more to do. dashboard.js
        # and chart_configs_js are empty.
        return out, "", ""

    script_body = m.group(1)
    data_js, helpers_js = _split_inline_script(script_body)

    # 4. Build the dashboard.js file content. Helpers + delegation glue.
    dashboard_js = helpers_js.rstrip() + "\n\n" + _EVENT_DELEGATION_JS.lstrip()

    # 5. Build the per-page chart-configs file content.
    chart_configs_js = data_js.rstrip() + "\n"

    # 6. Replace the inline <script>...</script> in the HTML with two
    #    external <script src="..."> tags. Per-page configs FIRST so they
    #    define CHART_CONFIGS / NO_DEFAULT_ZOOM before dashboard.js runs.
    external_scripts = (
        f'<script src="chart-configs-{page_slug}.js"></script>\n'
        f'  <script src="dashboard.js"></script>'
    )
    out = out.replace(m.group(0), external_scripts, 1)

    return out, dashboard_js, chart_configs_js
