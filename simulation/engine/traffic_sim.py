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
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

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
    od_breakdown: Optional[Dict[str, Dict[str, int]]] = None,
    corridor_paths: Optional[Dict[Tuple[str, str], List[str]]] = None,
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

    # Compute carpool vehicle savings per time slot
    carpool_savings_per_slot = _compute_carpool_savings_per_slot(
        carpool_groups, time_slots
    )

    # Parse modal split into working structures
    car_share, mcy_share, transit_share = _parse_modal_split(modal_split)
    car_occupancy = modal_split.get("CAR", {}).get("avg_occupancy", 1.2)
    mcy_occupancy = modal_split.get("MCY", {}).get("avg_occupancy", 1.0)

    # Build the per-corridor demand matrix. With OD breakdown + path lookup,
    # we route every (home_zone, office_zone) trip onto the actual corridors
    # it traverses — capturing through-traffic and giving each road realistic
    # demand. Without OD info, fall back to the older zone-match heuristic.
    od_demand_matrix: Optional[Dict[Tuple[str, str], np.ndarray]] = None
    if od_breakdown is not None and corridor_paths is not None:
        corridor_demand_matrix, od_demand_matrix = _build_corridor_demand_via_od(
            effective_companies, od_breakdown, corridor_paths,
            corridors, time_slots,
        )
    else:
        logger.warning(
            "No OD breakdown or corridor paths supplied; falling back to "
            "zone-match heuristic which ignores through-traffic"
        )
        person_demand = _generate_aggregate_demand(effective_companies, time_slots)
        corridors_to_zone_count: Dict[str, int] = {}
        for corridor in corridors:
            zone_to = corridor["zone_to"]
            corridors_to_zone_count[zone_to] = corridors_to_zone_count.get(zone_to, 0) + 1
        corridor_demand_matrix = np.array([
            _scale_demand_to_corridor(
                person_demand, c, effective_companies, time_slots,
                corridors_to_zone_count,
            )
            for c in corridors
        ], dtype=np.float64)

    base_car_matrix = (corridor_demand_matrix * car_share) / car_occupancy
    base_mcy_matrix = (corridor_demand_matrix * mcy_share) / mcy_occupancy

    # Distribute carpool savings proportionally to each corridor's share of
    # cars in that slot, capped at 50% of any single corridor's car volume.
    system_car_per_slot = base_car_matrix.sum(axis=0)
    with np.errstate(divide="ignore", invalid="ignore"):
        corridor_share_of_cars = np.where(
            system_car_per_slot > 0,
            base_car_matrix / system_car_per_slot,
            0.0,
        )
    proposed_reduction = corridor_share_of_cars * carpool_savings_per_slot[np.newaxis, :]
    per_corridor_cap = base_car_matrix * 0.5
    carpool_reduction_matrix = np.minimum(proposed_reduction, per_corridor_cap)
    car_matrix = np.maximum(base_car_matrix - carpool_reduction_matrix, 0)

    logger.debug(
        "Carpool reduction applied: requested=%.0f vehicles/day, "
        "actual=%.0f vehicles/day after per-corridor caps",
        float(carpool_savings_per_slot.sum()),
        float(carpool_reduction_matrix.sum()),
    )

    # Simulate each corridor. The travel_time_matrix captures BPR time per
    # corridor per slot so the OD commute aggregator (in routing.py) can
    # sum path times by origin/destination.
    num_slots = len(time_slots)
    travel_time_matrix = np.zeros_like(corridor_demand_matrix)
    corridor_data: List[dict] = []
    peak_congestion = 0.0
    weighted_travel_time = 0.0
    total_volume_for_avg = 0.0
    total_vehicle_km = 0.0

    for c_idx, corridor in enumerate(corridors):
        capacity_per_slot = corridor["capacity_vph"] * _SLOT_DURATION_HOURS
        free_flow_time_min = (
            corridor["distance_km"] / corridor["free_flow_speed_kmh"]
        ) * 60

        for slot_idx, t in enumerate(time_slots):
            car_vehicles = float(car_matrix[c_idx, slot_idx])
            mcy_vehicles = float(base_mcy_matrix[c_idx, slot_idx])

            pce_volume = (car_vehicles * _PCE_CAR) + (mcy_vehicles * _PCE_MOTORCYCLE)

            slot_travel_time = travel_time(
                free_flow_time=free_flow_time_min,
                volume=pce_volume,
                capacity=capacity_per_slot,
                alpha=corridor.get("bpr_alpha", 0.15),
                beta=corridor.get("bpr_beta", 4.0),
            )
            travel_time_matrix[c_idx, slot_idx] = slot_travel_time

            speed = (
                corridor["distance_km"] / (slot_travel_time / 60)
                if slot_travel_time > 0
                else corridor["free_flow_speed_kmh"]
            )
            cong_idx = congestion_index(pce_volume, capacity_per_slot)

            hour = int(t)
            minute = int((t - hour) * 60)
            time_label = f"{hour:02d}:{minute:02d}"

            corridor_data.append({
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
                "congestion_level": round(min(cong_idx, 1.0), 4),
            })

            peak_congestion = max(peak_congestion, cong_idx)
            if pce_volume > 0:
                weighted_travel_time += slot_travel_time * pce_volume
                total_volume_for_avg += pce_volume
            total_vehicle_km += pce_volume * corridor["distance_km"]

    avg_travel_time = (
        weighted_travel_time / total_volume_for_avg
        if total_volume_for_avg > 0
        else 0
    )

    # System-wide peak vehicles: count UNIQUE vehicles entering the road
    # in the worst 15-min slot, not the per-corridor max (under-counted by
    # ignoring everything but the worst single road) or the sum across
    # corridors (over-counted because a multi-hop trip touches each corridor
    # on its path). Using od_demand gives us each trip exactly once.
    if od_demand_matrix:
        od_persons_per_slot = np.zeros(num_slots, dtype=np.float64)
        for arr in od_demand_matrix.values():
            od_persons_per_slot = od_persons_per_slot + arr
        unique_cars = (od_persons_per_slot * car_share) / car_occupancy
        unique_motos = (od_persons_per_slot * mcy_share) / mcy_occupancy
        unique_vehicles_per_slot = np.maximum(
            unique_cars + unique_motos - carpool_savings_per_slot, 0
        )
        peak_vehicles_system = int(round(float(unique_vehicles_per_slot.max())))
    else:
        # Fallback when OD info is absent — corridor sum over-counts but
        # is at least monotonic with congestion.
        system_vehicles_per_slot = (car_matrix + base_mcy_matrix).sum(axis=0)
        peak_vehicles_system = int(round(float(system_vehicles_per_slot.max())))

    summary = {
        "peak_congestion": round(min(peak_congestion, 1.0), 4),
        "avg_travel_time_min": round(avg_travel_time, 2),
        "peak_vehicles": peak_vehicles_system,
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

    return {
        "corridor_data": corridor_data,
        "summary": summary,
        "travel_time_matrix": travel_time_matrix,
        "corridor_codes": [c["code"] for c in corridors],
        "od_demand": od_demand_matrix,
    }


def _build_corridor_demand_via_od(
    effective_companies: List[dict],
    od_breakdown: Dict[str, Dict[str, int]],
    corridor_paths: Dict[Tuple[str, str], List[str]],
    corridors: List[dict],
    time_slots: List[float],
) -> Tuple[np.ndarray, Dict[Tuple[str, str], np.ndarray]]:
    """
    Build the per-corridor demand matrix by routing each OD pair's trips
    along its shortest-path corridor sequence.

    Args:
        effective_companies: Company dicts after WFH reduction (so the
            scaling honors the day's available headcount).
        od_breakdown: company_code -> {home_zone: original_staff_count}.
            Counts come from the raw staff list; we rescale by each
            company's current effective total_staff so WFH/stagger flow
            through correctly.
        corridor_paths: (home_zone, office_zone) -> ordered list of
            corridor codes on the shortest path. Missing keys mean the
            pair is unreachable and its trips are skipped.
        corridors: List of corridor dicts (for index lookup).
        time_slots: Slot centers in hours.

    Returns:
        (corridor_demand_matrix, od_demand_matrix)
        - corridor_demand_matrix: shape (num_corridors, num_slots),
          person-trips per corridor per slot.
        - od_demand_matrix: dict (home, office) -> shape (num_slots,)
          person-trips. Used downstream for OD-based commute averaging.
    """
    num_corridors = len(corridors)
    num_slots = len(time_slots)
    corridor_idx = {c["code"]: i for i, c in enumerate(corridors)}

    corridor_demand = np.zeros((num_corridors, num_slots), dtype=np.float64)
    od_demand: Dict[Tuple[str, str], np.ndarray] = defaultdict(
        lambda: np.zeros(num_slots, dtype=np.float64)
    )

    skipped_trips = 0
    for company in effective_companies:
        if company["total_staff"] <= 0:
            continue
        home_dist = od_breakdown.get(company["code"], {})
        if not home_dist:
            continue
        original_total = sum(home_dist.values())
        if original_total <= 0:
            continue

        scale = company["total_staff"] / original_total
        std_dev = company.get("std_dev", _DEFAULT_STD_DEV)
        morning_mean = company["start_hour"] - _DEPARTURE_OFFSET_HOURS
        return_mean = company["start_hour"] + 8.5
        return_std = std_dev * 1.3
        office_zone = company["office_zone"]

        for home_zone, raw_count in home_dist.items():
            count = int(round(raw_count * scale))
            if count <= 0:
                continue

            morning = generate_demand_profile(
                time_slots, morning_mean, std_dev, count
            ).astype(np.float64)
            afternoon = generate_demand_profile(
                time_slots, return_mean, return_std, count
            ).astype(np.float64)
            od_total = morning + afternoon

            od_demand[(home_zone, office_zone)] += od_total

            path = corridor_paths.get((home_zone, office_zone))
            if path is None:
                skipped_trips += count
                continue
            for code in path:
                idx = corridor_idx.get(code)
                if idx is not None:
                    corridor_demand[idx] += od_total

    if skipped_trips > 0:
        logger.warning(
            "OD routing: %d person-trips/day from unreachable zone pairs "
            "were not assigned to any corridor",
            skipped_trips,
        )

    return corridor_demand, dict(od_demand)


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
            # Use the pre-computed wfh_fraction set in the runner — accounts
            # for both company policy (wfh_days_per_week) and run-level
            # eligibility. Default formula here is a fallback for direct
            # callers that don't go through the runner.
            wfh_fraction = company.get(
                "wfh_fraction",
                min((company.get("wfh_days_per_week", 1) / 5.0) * 0.8, 0.6),
            )
            entry["total_staff"] = int(
                company["total_staff"] * (1 - wfh_fraction)
            )
            logger.debug(
                "Company %s: WFH active on day %d (%.0f%% reduction), staff %d -> %d",
                code,
                day_of_week,
                wfh_fraction * 100,
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


def _compute_carpool_savings_per_slot(
    carpool_groups: List[dict],
    time_slots: List[float],
) -> np.ndarray:
    """
    Distribute carpool vehicle savings across time slots based on departure times.

    Each carpool group saves (num_passengers) vehicles concentrated around
    its departure time using a narrow Gaussian.
    """
    savings = np.zeros(len(time_slots), dtype=np.float64)
    slots_array = np.array(time_slots, dtype=np.float64)

    total_saved = 0
    for group in carpool_groups:
        passengers = len(group.get("passenger_ids", []))
        if passengers <= 0:
            continue

        departure = group.get("departure_time", 7.5)
        # Distribute savings as a narrow Gaussian around departure time
        weights = np.exp(-0.5 * ((slots_array - departure) / 0.5) ** 2)
        weight_sum = weights.sum()
        if weight_sum > 0:
            savings += (weights / weight_sum) * passengers
        total_saved += passengers

    logger.debug(
        "Carpool vehicle savings: %d passengers across %d groups, "
        "peak slot savings=%.1f",
        total_saved,
        len(carpool_groups),
        savings.max() if len(savings) > 0 else 0,
    )

    return savings


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
    """Generate aggregate person-trip demand across all companies.

    Includes both morning outbound and afternoon return trips.
    Return trips are centered ~8.5 hours after start with wider spread.
    """
    aggregate = np.zeros(len(time_slots), dtype=np.float64)

    for company in companies:
        if company["total_staff"] <= 0:
            continue

        std_dev = company.get("std_dev", _DEFAULT_STD_DEV)
        staff = company["total_staff"]

        # Morning outbound trip
        mean_departure = company["start_hour"] - _DEPARTURE_OFFSET_HOURS
        morning = generate_demand_profile(
            time_slots, mean_departure, std_dev, staff
        )
        aggregate += morning.astype(np.float64)

        # Afternoon return trip (~8.5h after start, wider spread)
        return_mean = company["start_hour"] + 8.5
        return_std = std_dev * 1.3
        afternoon = generate_demand_profile(
            time_slots, return_mean, return_std, staff
        )
        aggregate += afternoon.astype(np.float64)

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
    corridors_to_zone_count: Dict[str, int] = None,
) -> np.ndarray:
    """
    Scale aggregate demand to a specific corridor.

    Uses zone-matching: companies whose office_zone matches the corridor's
    destination zone contribute demand. Demand is split among all corridors
    serving the same destination zone to prevent double-counting.
    """
    corridor_zone_to = corridor["zone_to"]
    corridor_zone_from = corridor["zone_from"]
    total_staff_all = sum(c["total_staff"] for c in companies)

    if total_staff_all <= 0:
        return np.zeros(len(time_slots), dtype=np.float64)

    # Staff going to this corridor's destination zone
    matching_staff = sum(
        c["total_staff"]
        for c in companies
        if c.get("office_zone") == corridor_zone_to
    )

    # Also count staff coming FROM the origin zone (for return trips)
    from_staff = sum(
        c["total_staff"]
        for c in companies
        if c.get("office_zone") == corridor_zone_from
    )

    # Use the larger of to/from to capture both directions
    relevant_staff = max(matching_staff, from_staff)

    if relevant_staff > 0:
        fraction = relevant_staff / total_staff_all
    else:
        # Background traffic fraction for corridors with no direct company match
        num_corridors = len(time_slots) and max(len(companies), 1)
        fraction = 0.05  # 5% background traffic

    # Split among corridors serving the same destination zone
    if corridors_to_zone_count and corridor_zone_to in corridors_to_zone_count:
        num_serving = corridors_to_zone_count[corridor_zone_to]
        if num_serving > 1:
            # Weight by corridor capacity relative to total capacity for this zone
            fraction = fraction / num_serving

    corridor_demand = person_demand * fraction

    logger.debug(
        "Corridor %s (%s->%s): demand fraction=%.4f, peak=%.0f",
        corridor["code"],
        corridor_zone_from,
        corridor_zone_to,
        fraction,
        corridor_demand.max(),
    )

    return corridor_demand
