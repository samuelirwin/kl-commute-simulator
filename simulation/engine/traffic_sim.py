"""
Mesoscopic traffic simulator.

Time-sliced (15-minute intervals from 6:00 AM to 10:00 PM = 64 slots)
BPR-based simulation that models vehicle flow across KL corridors. For each
corridor at each time slice, the simulator:

1. Computes demand from overlaid company Gaussian departure profiles
2. Applies modal split to convert person-trips to vehicle volumes
3. Accounts for motorcycle PCE (0.5) and transit absorption
4. Computes travel time using the BPR volume-delay function
5. Derives speed and congestion metrics

This is a mesoscopic model: individual vehicles are not tracked, but
aggregate flows are resolved at a finer granularity than macroscopic models.
"""

import logging
from typing import Dict, List

import numpy as np

from simulation.engine.bpr import congestion_index, travel_time
from simulation.engine.demand import generate_demand_profile

logger = logging.getLogger("simulation")

# Simulation time configuration
_SIM_START_HOUR = 6.0     # 6:00 AM
_SIM_END_HOUR = 22.0      # 10:00 PM
_SLOT_DURATION_HOURS = 0.25  # 15 minutes
_NUM_SLOTS = int((_SIM_END_HOUR - _SIM_START_HOUR) / _SLOT_DURATION_HOURS)

# Passenger Car Equivalent (PCE) factors
_PCE_CAR = 1.0
_PCE_MOTORCYCLE = 0.5

# Default departure offset: staff leave ~45 min before start time
_DEPARTURE_OFFSET_HOURS = 0.75

# Default demand spread (std dev in hours)
_DEFAULT_STD_DEV = 0.5


def generate_time_slots() -> List[float]:
    """Generate the list of time slot center-points for the simulation day."""
    return [
        _SIM_START_HOUR + i * _SLOT_DURATION_HOURS
        for i in range(_NUM_SLOTS)
    ]


def run_traffic_simulation(
    corridors: List[dict],
    companies: List[dict],
    modal_split: Dict[str, dict],
    stagger_plan: Dict[str, float],
    wfh_plan: Dict[str, List[int]],
    carpool_groups: List[dict],
    day_of_week: int,
) -> dict:
    """
    Run a full-day mesoscopic traffic simulation.

    Args:
        corridors: List of dicts with keys:
            - code: str
            - zone_from: str
            - zone_to: str
            - distance_km: float
            - free_flow_speed_kmh: float
            - capacity_vph: int (vehicles per hour)
            - bpr_alpha: float
            - bpr_beta: float
        companies: List of dicts with keys:
            - code: str
            - total_staff: int
            - office_zone: str
            - start_hour: float (may be overridden by stagger_plan)
        modal_split: Dict mapping mode code -> dict with:
            - share_pct: float
            - avg_occupancy: float
        stagger_plan: Dict mapping company_code -> optimized start_hour.
            If empty, default start hours are used.
        wfh_plan: Dict mapping company_code -> list of WFH day indices.
            Staff on WFH are excluded from demand on matching days.
        carpool_groups: List of carpool group dicts (from carpool matcher).
            Used to reduce vehicle count through shared rides.
        day_of_week: Integer 0-4 (Mon-Fri) for WFH day matching.

    Returns:
        Dict with keys:
            - corridor_data: list of dicts, one per (corridor, time_slot)
            - summary: dict with peak_congestion, avg_travel_time_min,
              peak_vehicles, total_vehicle_km
    """
    time_slots = generate_time_slots()

    logger.info(
        "Starting traffic simulation: %d corridors, %d companies, "
        "day=%d, %d time slots",
        len(corridors),
        len(companies),
        day_of_week,
        len(time_slots),
    )

    # Compute effective staff per company after WFH reduction
    effective_companies = _apply_wfh_reduction(
        companies, wfh_plan, day_of_week
    )

    # Apply stagger plan to override start hours
    _apply_stagger_plan(effective_companies, stagger_plan)

    # Compute carpool vehicle savings
    carpool_savings = _compute_carpool_vehicle_savings(carpool_groups)

    # Parse modal split into working structures
    car_share, mcy_share, transit_share = _parse_modal_split(modal_split)
    car_occupancy = modal_split.get("CAR", {}).get("avg_occupancy", 1.2)
    mcy_occupancy = modal_split.get("MCY", {}).get("avg_occupancy", 1.0)

    # Generate aggregate demand profile (person-trips per time slot)
    person_demand = _generate_aggregate_demand(effective_companies, time_slots)

    # Simulate each corridor
    corridor_data: List[dict] = []
    peak_congestion = 0.0
    total_travel_time = 0.0
    total_vehicles_counted = 0
    peak_vehicles = 0
    total_vehicle_km = 0.0
    travel_time_entries = 0

    for corridor in corridors:
        # Scale demand to this corridor based on zone relevance
        corridor_demand = _scale_demand_to_corridor(
            person_demand, corridor, effective_companies, time_slots
        )

        capacity_per_slot = corridor["capacity_vph"] * _SLOT_DURATION_HOURS
        free_flow_time_min = (
            corridor["distance_km"] / corridor["free_flow_speed_kmh"]
        ) * 60

        for slot_idx, t in enumerate(time_slots):
            persons = corridor_demand[slot_idx]

            # Convert person-trips to vehicle volumes by mode
            car_vehicles = (persons * car_share) / car_occupancy
            mcy_vehicles = (persons * mcy_share) / mcy_occupancy
            transit_absorbed = persons * transit_share

            # Apply carpool reduction to car vehicles
            carpool_reduction = min(
                carpool_savings * _SLOT_DURATION_HOURS,
                car_vehicles * 0.3,  # Cap at 30% of car volume per slot
            )
            car_vehicles = max(car_vehicles - carpool_reduction, 0)

            # Total PCE volume
            pce_volume = (car_vehicles * _PCE_CAR) + (mcy_vehicles * _PCE_MOTORCYCLE)

            # BPR travel time
            slot_travel_time = travel_time(
                free_flow_time=free_flow_time_min,
                volume=pce_volume,
                capacity=capacity_per_slot,
                alpha=corridor.get("bpr_alpha", 0.15),
                beta=corridor.get("bpr_beta", 4.0),
            )

            # Derived metrics
            speed = (
                corridor["distance_km"] / (slot_travel_time / 60)
                if slot_travel_time > 0
                else corridor["free_flow_speed_kmh"]
            )
            cong_idx = congestion_index(pce_volume, capacity_per_slot)

            # Format time slot label
            hour = int(t)
            minute = int((t - hour) * 60)
            time_label = f"{hour:02d}:{minute:02d}"

            record = {
                "corridor_code": corridor["code"],
                "zone_from": corridor["zone_from"],
                "zone_to": corridor["zone_to"],
                "time_slot": time_label,
                "time_hour": t,
                "volume_pce": round(pce_volume),
                "volume_car": round(car_vehicles),
                "volume_motorcycle": round(mcy_vehicles),
                "capacity": round(capacity_per_slot),
                "capacity_ratio": round(pce_volume / capacity_per_slot, 4) if capacity_per_slot > 0 else 0,
                "travel_time_min": round(slot_travel_time, 2),
                "speed_kmh": round(speed, 1),
                "congestion_level": round(min(cong_idx, 2.0), 4),
            }
            corridor_data.append(record)

            # Update summary accumulators
            peak_congestion = max(peak_congestion, cong_idx)
            total_travel_time += slot_travel_time
            travel_time_entries += 1
            slot_vehicle_total = round(car_vehicles + mcy_vehicles)
            peak_vehicles = max(peak_vehicles, slot_vehicle_total)
            total_vehicle_km += pce_volume * corridor["distance_km"]

    avg_travel_time = (
        total_travel_time / travel_time_entries
        if travel_time_entries > 0
        else 0
    )

    summary = {
        "peak_congestion": round(peak_congestion, 4),
        "avg_travel_time_min": round(avg_travel_time, 2),
        "peak_vehicles": peak_vehicles,
        "total_vehicle_km": round(total_vehicle_km, 1),
        "num_corridors": len(corridors),
        "num_time_slots": len(time_slots),
        "num_records": len(corridor_data),
    }

    logger.info(
        "Simulation complete: peak_congestion=%.4f, avg_travel=%.2f min, "
        "peak_vehicles=%d, total_vkm=%.0f",
        summary["peak_congestion"],
        summary["avg_travel_time_min"],
        summary["peak_vehicles"],
        summary["total_vehicle_km"],
    )

    return {"corridor_data": corridor_data, "summary": summary}


def _apply_wfh_reduction(
    companies: List[dict],
    wfh_plan: Dict[str, List[int]],
    day_of_week: int,
) -> List[dict]:
    """
    Create modified company list with staff reduced for WFH on the given day.

    Returns new list (does not mutate originals).
    """
    effective = []

    for company in companies:
        entry = dict(company)  # Shallow copy
        code = company["code"]

        if code in wfh_plan and day_of_week in wfh_plan[code]:
            # Assume WFH staff proportion is roughly (wfh_days / 5)
            # but the plan tells us which specific days
            wfh_fraction = 0.2  # Default: ~20% WFH on their assigned day
            entry["total_staff"] = int(
                company["total_staff"] * (1 - wfh_fraction)
            )
            logger.debug(
                "Company %s: WFH active on day %d, staff %d -> %d",
                code,
                day_of_week,
                company["total_staff"],
                entry["total_staff"],
            )

        effective.append(entry)

    return effective


def _apply_stagger_plan(
    companies: List[dict],
    stagger_plan: Dict[str, float],
) -> None:
    """Apply stagger plan start hours to company entries (mutates in place)."""
    for company in companies:
        code = company["code"]
        if code in stagger_plan:
            original = company["start_hour"]
            company["start_hour"] = stagger_plan[code]
            logger.debug(
                "Company %s: staggered start %.2f -> %.2f",
                code,
                original,
                stagger_plan[code],
            )


def _compute_carpool_vehicle_savings(carpool_groups: List[dict]) -> float:
    """
    Count total vehicles saved by carpooling (per hour equivalent).

    Each carpool group with passengers saves (num_passengers) vehicles,
    distributed across a 1-hour departure window.
    """
    total_passengers_saved = sum(
        len(g.get("passenger_ids", [])) for g in carpool_groups
    )

    logger.debug(
        "Carpool vehicle savings: %d passengers across %d groups",
        total_passengers_saved,
        len(carpool_groups),
    )

    return float(total_passengers_saved)


def _parse_modal_split(
    modal_split: Dict[str, dict],
) -> tuple:
    """
    Extract car, motorcycle, and transit share fractions from modal split.

    Returns (car_fraction, motorcycle_fraction, transit_fraction) as floats
    summing to approximately 1.0. E-hailing is merged with car.
    """
    total = sum(m.get("share_pct", 0) for m in modal_split.values())
    if total <= 0:
        logger.warning("Modal split total is 0; defaulting to 100%% car")
        return 1.0, 0.0, 0.0

    car_pct = modal_split.get("CAR", {}).get("share_pct", 0)
    ehl_pct = modal_split.get("EHL", {}).get("share_pct", 0)
    mcy_pct = modal_split.get("MCY", {}).get("share_pct", 0)
    pub_pct = modal_split.get("PUB", {}).get("share_pct", 0)

    car_share = (car_pct + ehl_pct) / total
    mcy_share = mcy_pct / total
    transit_share = pub_pct / total

    logger.debug(
        "Modal split parsed: car=%.1f%%, motorcycle=%.1f%%, transit=%.1f%%",
        car_share * 100,
        mcy_share * 100,
        transit_share * 100,
    )

    return car_share, mcy_share, transit_share


def _generate_aggregate_demand(
    companies: List[dict],
    time_slots: List[float],
) -> np.ndarray:
    """Generate aggregate person-trip demand across all companies."""
    aggregate = np.zeros(len(time_slots), dtype=np.float64)

    for company in companies:
        if company["total_staff"] <= 0:
            continue

        mean_departure = company["start_hour"] - _DEPARTURE_OFFSET_HOURS
        std_dev = company.get("std_dev", _DEFAULT_STD_DEV)

        profile = generate_demand_profile(
            time_slots, mean_departure, std_dev, company["total_staff"]
        )
        aggregate += profile.astype(np.float64)

    logger.debug(
        "Aggregate demand: total=%.0f person-trips, peak=%.0f at slot index %d",
        aggregate.sum(),
        aggregate.max(),
        int(np.argmax(aggregate)),
    )

    return aggregate


def _scale_demand_to_corridor(
    person_demand: np.ndarray,
    corridor: dict,
    companies: List[dict],
    time_slots: List[float],
) -> np.ndarray:
    """
    Scale aggregate demand to a specific corridor.

    Uses a simple zone-matching heuristic: companies whose office_zone
    matches the corridor's zone_to contribute their share of demand to
    this corridor. If no company matches, a uniform fraction is applied.
    """
    corridor_zone_to = corridor["zone_to"]
    total_staff_all = sum(c["total_staff"] for c in companies)

    if total_staff_all <= 0:
        return np.zeros(len(time_slots), dtype=np.float64)

    # Staff going to this corridor's destination zone
    matching_staff = sum(
        c["total_staff"]
        for c in companies
        if c.get("office_zone") == corridor_zone_to
    )

    if matching_staff > 0:
        fraction = matching_staff / total_staff_all
    else:
        # No direct match; apply a small background fraction
        num_corridors = max(1, 10)  # Estimate; prevents over-allocation
        fraction = 1.0 / num_corridors

    corridor_demand = person_demand * fraction

    logger.debug(
        "Corridor %s (%s->%s): demand fraction=%.4f, peak=%.0f",
        corridor["code"],
        corridor["zone_from"],
        corridor_zone_to,
        fraction,
        corridor_demand.max(),
    )

    return corridor_demand
