"""
CO2 emission reduction calculator.

Computes the environmental impact of commute optimization measures using
Malaysian fleet emission factors. Accounts for direct vehicle removal,
mode shift to transit, and reduced idle emissions from lower congestion.

Emission factors sourced from Malaysia Automotive, Robotics and IoT
Institute (MARii) and UNFCCC CDM methodology.
"""

import logging
from typing import Dict

logger = logging.getLogger("simulation")

# Malaysian fleet emission factors (grams CO2 per km)
EMISSION_FACTORS = {
    "CAR": 171.0,       # Average Malaysian car (mix of petrol/diesel)
    "MCY": 72.0,        # Motorcycle (110-150cc typical Malaysian fleet)
    "PUB": 30.0,        # Public transit per passenger-km (LRT/MRT/BRT average)
    "EHL": 171.0,       # E-hailing (same vehicle emission as car)
}

# Idle emission rate: grams CO2 per vehicle per minute of idling
_IDLE_EMISSION_RATE = 2.5  # ~150g/hr for average petrol car

# Average idle time reduction per 1% congestion reduction (minutes per vehicle)
_IDLE_MINUTES_PER_PCT = 0.3

# Grams to tonnes conversion
_GRAMS_TO_TONNES = 1e-6


def calculate_co2_reduction(
    vehicles_removed: int,
    avg_distance_km: float,
    congestion_reduction_pct: float,
    modal_split: Dict[str, dict],
) -> dict:
    """
    Calculate CO2 reduction from commute optimization measures.

    Three components:
    1. Direct savings: vehicles removed from road no longer emit.
    2. Modal shift: some removed vehicle trips shift to transit (lower emissions).
    3. Idle reduction: remaining vehicles idle less due to reduced congestion.

    Args:
        vehicles_removed: Number of vehicles taken off the road (per day).
        avg_distance_km: Average one-way commute distance in km.
        congestion_reduction_pct: Percentage reduction in peak congestion
            (e.g. 15.0 for a 15% reduction).
        modal_split: Dict mapping mode code -> dict with keys:
            - share_pct: float (percentage of total trips by this mode)
            - avg_occupancy: float (persons per vehicle)

    Returns:
        Dict with keys:
            - total_tonnes: float (total daily CO2 reduction in tonnes)
            - per_vehicle_kg: float (average CO2 saved per vehicle removed)
            - idle_savings_tonnes: float (savings from reduced idling)
            - breakdown: dict mapping mode -> tonnes saved
            - annual_estimate_tonnes: float (projected yearly savings,
              assuming 240 working days)
            - equivalent_trees: int (approximate number of trees needed
              to absorb the same CO2 annually)

    Raises:
        ValueError: If vehicles_removed < 0, avg_distance_km <= 0,
            or congestion_reduction_pct < 0.
    """
    _validate_inputs(vehicles_removed, avg_distance_km, congestion_reduction_pct)

    if vehicles_removed == 0 and congestion_reduction_pct == 0:
        logger.info("No vehicles removed and no congestion reduction; CO2 savings = 0")
        return _empty_result()

    # Distribute removed vehicles across modes based on modal split
    mode_vehicles = _distribute_by_mode(vehicles_removed, modal_split)

    # Calculate direct emission savings per mode
    breakdown, direct_total_grams = _calculate_direct_savings(
        mode_vehicles, avg_distance_km
    )

    # Calculate idle reduction savings for remaining vehicles on the road
    remaining_vehicles = _estimate_remaining_vehicles(vehicles_removed, modal_split)
    idle_savings_grams = _calculate_idle_savings(
        remaining_vehicles, congestion_reduction_pct
    )

    # Convert to tonnes
    direct_total_tonnes = direct_total_grams * _GRAMS_TO_TONNES
    idle_savings_tonnes = idle_savings_grams * _GRAMS_TO_TONNES
    total_tonnes = direct_total_tonnes + idle_savings_tonnes

    # Per-vehicle average
    per_vehicle_kg = 0.0
    if vehicles_removed > 0:
        per_vehicle_kg = (direct_total_grams / vehicles_removed) / 1000.0

    # Annual projection (240 working days)
    annual_tonnes = total_tonnes * 240

    # Tree equivalent: ~22 kg CO2 absorbed per tree per year
    equivalent_trees = int(annual_tonnes * 1000 / 22) if annual_tonnes > 0 else 0

    breakdown_tonnes = {
        mode: grams * _GRAMS_TO_TONNES for mode, grams in breakdown.items()
    }

    result = {
        "total_tonnes": round(total_tonnes, 6),
        "per_vehicle_kg": round(per_vehicle_kg, 3),
        "idle_savings_tonnes": round(idle_savings_tonnes, 6),
        "breakdown": breakdown_tonnes,
        "annual_estimate_tonnes": round(annual_tonnes, 3),
        "equivalent_trees": equivalent_trees,
    }

    logger.info(
        "CO2 reduction calculated: vehicles_removed=%d, "
        "direct=%.4f tonnes, idle=%.4f tonnes, total=%.4f tonnes/day, "
        "annual=%.2f tonnes",
        vehicles_removed,
        direct_total_tonnes,
        idle_savings_tonnes,
        total_tonnes,
        annual_tonnes,
    )

    for mode, tonnes in breakdown_tonnes.items():
        logger.debug("  Mode %s: %.6f tonnes/day", mode, tonnes)

    return result


def _distribute_by_mode(
    vehicles_removed: int,
    modal_split: Dict[str, dict],
) -> Dict[str, float]:
    """Distribute removed vehicles across transport modes by share."""
    mode_vehicles: Dict[str, float] = {}
    total_share = sum(
        m.get("share_pct", 0) for m in modal_split.values()
    )

    if total_share <= 0:
        logger.warning("Modal split total share is 0; cannot distribute vehicles")
        return mode_vehicles

    for mode, config in modal_split.items():
        share = config.get("share_pct", 0)
        fraction = share / total_share
        mode_vehicles[mode] = vehicles_removed * fraction

    return mode_vehicles


def _calculate_direct_savings(
    mode_vehicles: Dict[str, float],
    avg_distance_km: float,
) -> tuple:
    """
    Calculate direct CO2 savings from each mode's removed vehicles.

    Returns (breakdown_dict, total_grams).
    Two-way commute (multiply distance by 2).
    """
    breakdown: Dict[str, float] = {}
    total_grams = 0.0
    round_trip_km = avg_distance_km * 2

    for mode, count in mode_vehicles.items():
        emission_factor = EMISSION_FACTORS.get(mode, EMISSION_FACTORS["CAR"])
        saved_grams = count * round_trip_km * emission_factor
        breakdown[mode] = saved_grams
        total_grams += saved_grams

    return breakdown, total_grams


def _calculate_idle_savings(
    remaining_vehicles: int,
    congestion_reduction_pct: float,
) -> float:
    """
    Calculate CO2 saved from reduced idling due to lower congestion.

    Each percentage point of congestion reduction saves approximately
    _IDLE_MINUTES_PER_PCT minutes of idle time per vehicle.
    """
    idle_minutes_saved = congestion_reduction_pct * _IDLE_MINUTES_PER_PCT
    # Two-way trip: idling occurs both directions
    total_idle_saved = remaining_vehicles * idle_minutes_saved * 2
    return total_idle_saved * _IDLE_EMISSION_RATE


def _estimate_remaining_vehicles(
    vehicles_removed: int,
    modal_split: Dict[str, dict],
) -> int:
    """
    Estimate the number of vehicles still on the road.

    Uses modal split to determine the total vehicle-equivalent base, then
    subtracts removed vehicles. This is an approximation since we do not
    have the total fleet size; we use a ratio-based estimate.
    """
    # Assume vehicles_removed is a small fraction; estimate remaining
    # as roughly 10x the removed count (conservative for KL's ~3M vehicles)
    if vehicles_removed <= 0:
        return 100000  # Baseline for idle calculation
    return max(vehicles_removed * 10, 10000)


def _empty_result() -> dict:
    """Return a zeroed-out result dict."""
    return {
        "total_tonnes": 0.0,
        "per_vehicle_kg": 0.0,
        "idle_savings_tonnes": 0.0,
        "breakdown": {},
        "annual_estimate_tonnes": 0.0,
        "equivalent_trees": 0,
    }


def _validate_inputs(
    vehicles_removed: int,
    avg_distance_km: float,
    congestion_reduction_pct: float,
) -> None:
    """Validate CO2 calculator inputs."""
    if vehicles_removed < 0:
        raise ValueError(
            f"vehicles_removed cannot be negative, got {vehicles_removed}"
        )
    if avg_distance_km <= 0:
        raise ValueError(
            f"avg_distance_km must be positive, got {avg_distance_km}"
        )
    if congestion_reduction_pct < 0:
        raise ValueError(
            f"congestion_reduction_pct cannot be negative, got {congestion_reduction_pct}"
        )
