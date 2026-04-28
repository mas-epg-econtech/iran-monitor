"""
Narrative Regeneration Triggers
===============================

This module defines the conditions under which the LLM-generated dashboard
narrative should be regenerated. The narrative is an analyst-style
interpretation of the dashboard data, written by Claude and embedded in the
Overview tab.

The narrative is NOT regenerated on every data pipeline run. It is only
regenerated when at least one trigger fires. This keeps API costs low and
avoids producing near-identical narratives when the data hasn't meaningfully
changed.

Trigger evaluation flow:
  1. Pipeline finishes fetching new data
  2. Compute current summary stats (same as build_dashboard.py)
  3. Load previous summary stats from metadata ("narrative_prev_stats")
  4. Load previous narrative timestamp from metadata ("narrative_generated_at")
  5. Evaluate each trigger against current vs previous stats
  6. If ANY trigger fires → call Claude API → store new narrative + stats + timestamp
  7. If NO trigger fires → keep cached narrative

Each trigger has:
  - id:          Unique identifier for logging
  - description: Human-readable explanation of what it detects
  - category:    Grouping for audit purposes
  - threshold:   The numeric threshold that must be exceeded
  - rationale:   Why this threshold was chosen
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class Trigger:
    id: str
    description: str
    category: str
    threshold: float | None
    rationale: str
    check: Callable[[dict, dict], bool] | None = field(default=None, repr=False)


# ---------------------------------------------------------------------------
# Helper: percentage change between two values
# ---------------------------------------------------------------------------

def _pct(old: float | None, new: float | None) -> float | None:
    if old is None or new is None or old == 0:
        return None
    return (new - old) / abs(old) * 100


# ---------------------------------------------------------------------------
# Trigger definitions
# ---------------------------------------------------------------------------

TRIGGERS: list[Trigger] = [

    # ── Category: Time-based ──

    Trigger(
        id="time_fallback",
        description="More than 7 days since the last narrative was generated",
        category="Time-based",
        threshold=7,  # days
        rationale=(
            "Even if no data trigger fires, the narrative should not feel "
            "abandoned. A weekly refresh ensures it stays current with the "
            "broader context (e.g., news events the LLM may reference)."
        ),
    ),

    # ── Category: Upstream energy prices ──

    Trigger(
        id="crude_oil_move",
        description="Crude oil price moved more than 10% from the level at last narrative",
        category="Upstream energy prices",
        threshold=10,  # percent
        rationale=(
            "A 10% move in crude is a regime change that alters the narrative's "
            "conclusions about severity and passthrough. Smaller moves are noise "
            "in a volatile market."
        ),
    ),

    Trigger(
        id="nat_gas_move",
        description="US natural gas price moved more than 20% from the level at last narrative",
        category="Upstream energy prices",
        threshold=20,  # percent
        rationale=(
            "Natural gas has been stable during the conflict so far. A 20% move "
            "would signal the war is starting to affect gas markets (e.g., LNG "
            "disruption via Qatar), which is a significant narrative shift."
        ),
    ),

    # ── Category: Refined product prices ──

    Trigger(
        id="refined_product_move",
        description="Any Tier 2 product (VLSFO, jet fuel, gasoline, naphtha) moved more than 15%",
        category="Refined product prices",
        threshold=15,  # percent
        rationale=(
            "Tier 2 products can amplify or dampen the crude shock depending on "
            "refining margins. A 15% threshold (higher than crude's 10%) accounts "
            "for normal spread volatility while catching genuine breakouts."
        ),
    ),

    # ── Category: Industrial input prices ──

    Trigger(
        id="ethylene_move",
        description="SE Asia ethylene price moved more than 20%",
        category="Industrial input prices",
        threshold=20,  # percent
        rationale=(
            "Ethylene is the key Tier 3 indicator. A 20% move signals that "
            "feedstock cost pressure is transmitting (or easing) through the "
            "petrochemical chain, which affects the passthrough analysis."
        ),
    ),

    Trigger(
        id="passthrough_ratio_shift",
        description="The polymer-to-ethylene passthrough ratio changed by more than 15 percentage points",
        category="Industrial input prices",
        threshold=15,  # percentage points
        rationale=(
            "If ethylene is up 80% but polymers were up 40% (ratio ~0.5) and now "
            "polymers are up 70% (ratio ~0.88), that's a meaningful shift — it "
            "means cost pressure is no longer being absorbed by demand destruction "
            "and is passing through to end products."
        ),
    ),

    # ── Category: Singapore consumer prices ──

    Trigger(
        id="pump_price_move",
        description="Any Singapore pump price (diesel, RON 92/95/98) moved more than 10%",
        category="Singapore consumer prices",
        threshold=10,  # percent
        rationale=(
            "Pump prices are politically visible and affect household budgets "
            "directly. A 10% move is enough to warrant narrative attention, "
            "especially given Singapore's small price movements historically."
        ),
    ),

    Trigger(
        id="diesel_petrol_inversion",
        description="The diesel vs petrol price relationship inverted or reverted",
        category="Singapore consumer prices",
        threshold=None,  # binary event
        rationale=(
            "Diesel being more expensive than petrol is structurally unusual and "
            "was flagged as a key observation. If it reverts, that's equally "
            "noteworthy — it would suggest the refining bottleneck is easing."
        ),
    ),

    Trigger(
        id="electricity_tariff_change",
        description="Electricity tariff changed by any amount (it moves in discrete quarterly steps)",
        category="Singapore consumer prices",
        threshold=0.5,  # cents/kWh — any real change
        rationale=(
            "The tariff is an administered price that moves in large quarterly "
            "steps. Any change is a discrete event worth narrating because it "
            "signals the EMA has incorporated the energy shock into forward "
            "pricing. The current narrative specifically calls out the flat "
            "tariff as a lagging indicator."
        ),
    ),

    # ── Category: Data coverage events ──

    Trigger(
        id="stale_series_becomes_fresh",
        description="A previously stale activity indicator gets new data covering the war period",
        category="Data coverage events",
        threshold=None,  # binary event
        rationale=(
            "This is one of the most important triggers. The narrative currently "
            "flags IPI and wholesale trade as blind spots. When they finally "
            "update with war-period data, the narrative needs to incorporate "
            "whatever they show — this could be the first real evidence of "
            "production cutbacks or trade volume changes."
        ),
    ),

    Trigger(
        id="series_goes_stale",
        description="A previously fresh series stops updating (no new data for 2x its expected frequency)",
        category="Data coverage events",
        threshold=None,  # binary event
        rationale=(
            "If a series that was updating weekly suddenly goes silent for two "
            "weeks, it may indicate a data source problem that the narrative "
            "should acknowledge rather than silently using stale data."
        ),
    ),

    # ── Category: Activity indicator inflections ──

    Trigger(
        id="port_activity_decline",
        description="Container throughput or sea cargo YoY growth turns negative",
        category="Activity indicator inflections",
        threshold=0,  # crossing zero
        rationale=(
            "Port activity has been growing 6-7% YoY through the war period so "
            "far. A turn to negative growth would be the first concrete evidence "
            "that higher shipping costs are reducing trade volumes — a major "
            "narrative event for Singapore as a transhipment hub."
        ),
    ),

    Trigger(
        id="ipi_sharp_decline",
        description="Any IPI sub-index drops below 85 on the 2019=100 base",
        category="Activity indicator inflections",
        threshold=85,  # index level
        rationale=(
            "An IPI reading below 85 represents a 15%+ decline from the base "
            "year, indicating severe production cutbacks. Petrochemicals was at "
            "73.8 in Dec 2025 (pre-war) so it may already be below this, but if "
            "it drops further with war-period data, that's significant."
        ),
    ),
]


# ---------------------------------------------------------------------------
# Evaluation logic (to be called from the data pipeline)
# ---------------------------------------------------------------------------

def evaluate_triggers(
    current_stats: dict,
    previous_stats: dict | None,
    last_narrative_timestamp: str | None,
) -> list[Trigger]:
    """
    Evaluate all triggers and return the list of those that fired.

    Parameters
    ----------
    current_stats : dict
        Summary stats computed from the current data (same format as
        compute_summary() in build_dashboard.py).
    previous_stats : dict | None
        Summary stats from when the narrative was last generated.
        None if no previous narrative exists (always regenerate).
    last_narrative_timestamp : str | None
        ISO timestamp of when the narrative was last generated.
        None if no previous narrative exists.

    Returns
    -------
    list[Trigger]
        Triggers that fired. Empty list means no regeneration needed.
    """
    from datetime import datetime, timezone

    fired: list[Trigger] = []

    # If no previous stats, always regenerate
    if previous_stats is None:
        return TRIGGERS  # all fire

    # ── Time-based ──
    if last_narrative_timestamp:
        try:
            last_dt = datetime.fromisoformat(last_narrative_timestamp.replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            days_since = (now - last_dt).total_seconds() / 86400
            if days_since >= 7:
                fired.append(_get("time_fallback"))
        except (ValueError, TypeError):
            fired.append(_get("time_fallback"))
    else:
        fired.append(_get("time_fallback"))

    # ── Crude oil ──
    crude_pct = _delta_pct(previous_stats, current_stats, "crude", "latest_value")
    if crude_pct is not None and abs(crude_pct) >= 10:
        fired.append(_get("crude_oil_move"))

    # ── Natural gas ──
    prev_gas = (previous_stats.get("nat_gas") or {}).get("pct_change")
    curr_gas = (current_stats.get("nat_gas") or {}).get("pct_change")
    if prev_gas is not None and curr_gas is not None:
        if abs(curr_gas - prev_gas) >= 20:
            fired.append(_get("nat_gas_move"))

    # ── Tier 2 products ──
    for label in ["VLSFO Bunker", "Jet Fuel NWE", "Gasoline 95 SG", "Naphtha SG"]:
        prev_item = _find_item(previous_stats.get("tier2", []), label)
        curr_item = _find_item(current_stats.get("tier2", []), label)
        if prev_item and curr_item:
            pct = _pct(prev_item.get("latest"), curr_item.get("latest"))
            if pct is not None and abs(pct) >= 15:
                fired.append(_get("refined_product_move"))
                break  # one is enough

    # ── Ethylene ──
    prev_eth = _find_item(previous_stats.get("tier3", []), "SE Asia Ethylene")
    curr_eth = _find_item(current_stats.get("tier3", []), "SE Asia Ethylene")
    if prev_eth and curr_eth:
        pct = _pct(prev_eth.get("latest"), curr_eth.get("latest"))
        if pct is not None and abs(pct) >= 20:
            fired.append(_get("ethylene_move"))

    # ── Passthrough ratio ──
    prev_ratio = _passthrough_ratio(previous_stats)
    curr_ratio = _passthrough_ratio(current_stats)
    if prev_ratio is not None and curr_ratio is not None:
        if abs(curr_ratio - prev_ratio) >= 15:
            fired.append(_get("passthrough_ratio_shift"))

    # ── Pump prices ──
    for label in ["Diesel", "RON 95", "RON 92"]:
        prev_item = _find_item(previous_stats.get("pump_prices", []), label)
        curr_item = _find_item(current_stats.get("pump_prices", []), label)
        if prev_item and curr_item:
            pct = _pct(prev_item.get("latest"), curr_item.get("latest"))
            if pct is not None and abs(pct) >= 10:
                fired.append(_get("pump_price_move"))
                break

    # ── Diesel-petrol inversion ──
    prev_diesel = _find_item(previous_stats.get("pump_prices", []), "Diesel")
    prev_r95 = _find_item(previous_stats.get("pump_prices", []), "RON 95")
    curr_diesel = _find_item(current_stats.get("pump_prices", []), "Diesel")
    curr_r95 = _find_item(current_stats.get("pump_prices", []), "RON 95")
    if all([prev_diesel, prev_r95, curr_diesel, curr_r95]):
        prev_inverted = (prev_diesel.get("latest") or 0) > (prev_r95.get("latest") or 0)
        curr_inverted = (curr_diesel.get("latest") or 0) > (curr_r95.get("latest") or 0)
        if prev_inverted != curr_inverted:
            fired.append(_get("diesel_petrol_inversion"))

    # ── Electricity tariff ──
    prev_elec = (previous_stats.get("electricity") or {}).get("latest")
    curr_elec = (current_stats.get("electricity") or {}).get("latest")
    if prev_elec is not None and curr_elec is not None:
        if abs(curr_elec - prev_elec) >= 0.5:
            fired.append(_get("electricity_tariff_change"))

    # ── Stale series becomes fresh ──
    prev_activity = {a["label"]: a for a in previous_stats.get("activity", [])}
    curr_activity = {a["label"]: a for a in current_stats.get("activity", [])}
    for label, curr in curr_activity.items():
        prev = prev_activity.get(label)
        if prev and not prev.get("covers_war") and curr.get("covers_war"):
            fired.append(_get("stale_series_becomes_fresh"))
            break

    # ── Series goes stale ──
    for label, curr in curr_activity.items():
        prev = prev_activity.get(label)
        if prev and prev.get("covers_war") and not curr.get("covers_war"):
            fired.append(_get("series_goes_stale"))
            break

    # Remove None entries (from _get failures)
    return [t for t in fired if t is not None]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get(trigger_id: str) -> Trigger | None:
    for t in TRIGGERS:
        if t.id == trigger_id:
            return t
    return None


def _find_item(items: list[dict], label: str) -> dict | None:
    for item in items:
        if item.get("label") == label:
            return item
    return None


def _delta_pct(prev: dict, curr: dict, section: str, key: str) -> float | None:
    prev_val = (prev.get(section) or {}).get(key)
    curr_val = (curr.get(section) or {}).get(key)
    return _pct(prev_val, curr_val)


def _passthrough_ratio(stats: dict) -> float | None:
    """Compute avg polymer % change / avg ethylene % change."""
    tier3 = stats.get("tier3", [])
    eth_pcts = [t["pct_change"] for t in tier3
                if "Ethylene" in t.get("label", "") and t.get("pct_change") is not None]
    poly_pcts = [t["pct_change"] for t in tier3
                 if "Ethylene" not in t.get("label", "") and t.get("pct_change") is not None]
    if not eth_pcts or not poly_pcts:
        return None
    avg_eth = sum(eth_pcts) / len(eth_pcts)
    avg_poly = sum(poly_pcts) / len(poly_pcts)
    if avg_eth == 0:
        return None
    return (avg_poly / avg_eth) * 100  # ratio as percentage
