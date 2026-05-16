"""
Staggered working hours optimizer.

Zone-aware greedy load-balancer: assigns each company a start time that
minimizes peak demand at the company's destination zone, subject to:

- A global stagger window (e.g. 07:00–10:30)
- A per-company max-shift bound from its default start time
- Optional per-sector constraints (e.g. Government 07:30–09:00)

Companies are processed largest-first so big workforces shape the load
landscape before smaller ones fit around them. The system-wide capacity
list serves as a tiebreaker — when two slots produce equal destination-zone
load, the slot with more spare global capacity wins.
"""

import logging
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("simulation")

_DEFAULT_MAX_SHIFT_HOURS = 2.0
_SLOT_STEP_HOURS = 0.5  # 30-minute candidate slots
_HALF_SLOT_TOLERANCE = 0.25 + 1e-9  # Within 15 min on either side of a slot


def optimize_stagger(
    companies: List[dict],
    time_slots: List[float],
    capacities: List[float],
    window: Tuple[float, float] = (7.0, 10.5),
    max_shift_hours: float = _DEFAULT_MAX_SHIFT_HOURS,
    sector_constraints: Optional[Dict[str, Tuple[float, float]]] = None,
) -> Dict[str, float]:
    """
    Assign company start times to minimize peak destination-zone load.

    Args:
        companies: List of dicts with keys:
            - code: str
            - total_staff: int
            - default_start_hour: float
            - office_zone: str (used for per-zone load balancing)
            - sector: str (used with sector_constraints if provided)
        time_slots: Simulation time slot centers in hours (15-min granularity).
        capacities: Per-slot system capacity. Used as a tiebreaker when two
            candidate slots produce equal destination-zone load.
        window: (earliest, latest) global stagger window in hours.
        max_shift_hours: Max ± shift a company can take from its default
            start hour. Default 2.0h.
        sector_constraints: Optional dict mapping sector name to
            (earliest_start_hour, latest_start_hour). Companies in that
            sector can only be assigned slots inside that range.

    Returns:
        Dict company_code -> assigned start_hour (float).

    Raises:
        ValueError: on inconsistent or empty inputs.
    """
    _validate_inputs(companies, time_slots, capacities, window)
    sector_constraints = sector_constraints or {}

    candidate_slots = _generate_candidate_slots(window, _SLOT_STEP_HOURS)
    if not candidate_slots:
        raise ValueError(
            f"Stagger window {window} too narrow to contain any slot"
        )

    capacity_lookup = _build_slot_capacity_lookup(
        time_slots, capacities, candidate_slots
    )

    logger.info(
        "Starting stagger optimization: %d companies, window=%.1f-%.1fh, "
        "max_shift=%.1fh, %d sector rules",
        len(companies), window[0], window[1], max_shift_hours,
        len(sector_constraints),
    )

    # Per-zone-per-slot load and global per-slot load
    zone_slot_load: Dict[str, Dict[float, float]] = defaultdict(
        lambda: {s: 0.0 for s in candidate_slots}
    )
    global_slot_load: Dict[float, float] = {s: 0.0 for s in candidate_slots}

    # Largest workforces first — they shape the landscape
    sorted_companies = sorted(
        companies, key=lambda c: c["total_staff"], reverse=True
    )

    assignments: Dict[str, float] = {}
    for company in sorted_companies:
        code = company["code"]
        zone = company.get("office_zone", "_UNZONED")
        sector = company.get("sector")
        staff = company["total_staff"]

        allowed = _allowed_slots_for_company(
            company=company,
            candidate_slots=candidate_slots,
            max_shift_hours=max_shift_hours,
            sector_constraints=sector_constraints,
        )

        # Primary: minimize peak load at this company's destination zone.
        # Tiebreaker: prefer slots with more spare global capacity.
        best_slot = min(
            allowed,
            key=lambda s: (
                zone_slot_load[zone][s] + staff,
                (global_slot_load[s] + staff) / max(capacity_lookup.get(s, 1.0), 1e-9),
            ),
        )
        assignments[code] = best_slot
        zone_slot_load[zone][best_slot] += staff
        global_slot_load[best_slot] += staff

        shift_minutes = (best_slot - company["default_start_hour"]) * 60
        logger.info(
            "Company %s [%s/%s]: default=%.2fh -> assigned=%.2fh (shift %+.0fmin)",
            code, sector or "-", zone,
            company["default_start_hour"], best_slot, shift_minutes,
        )

    for slot in candidate_slots:
        load = global_slot_load[slot]
        cap = capacity_lookup.get(slot, 0)
        pct = (load / cap * 100) if cap > 0 else 0
        logger.info(
            "Stagger slot %.1fh: %.0f staff assigned (%.0f%% of slot capacity)",
            slot, load, pct,
        )

    return assignments


def _allowed_slots_for_company(
    company: dict,
    candidate_slots: List[float],
    max_shift_hours: float,
    sector_constraints: Dict[str, Tuple[float, float]],
) -> List[float]:
    """
    Compute the slots a company can be assigned to.

    Intersect candidate_slots with [default ± max_shift] and the sector
    window. If the intersection is empty, fall back to the slot closest to
    default that still satisfies the sector constraint (or just the closest
    to default when no sector rule applies).
    """
    default = company["default_start_hour"]
    sector = company.get("sector")
    sector_min, sector_max = sector_constraints.get(
        sector, (float("-inf"), float("inf"))
    )

    lo = max(default - max_shift_hours, sector_min)
    hi = min(default + max_shift_hours, sector_max)

    allowed = [s for s in candidate_slots if lo <= s <= hi]
    if allowed:
        return allowed

    sector_allowed = [
        s for s in candidate_slots if sector_min <= s <= sector_max
    ]
    pool = sector_allowed or candidate_slots
    closest = min(pool, key=lambda s: abs(s - default))
    logger.warning(
        "Company %s: max_shift ±%.1fh conflicts with sector window for '%s'; "
        "falling back to %.2fh",
        company["code"], max_shift_hours, sector, closest,
    )
    return [closest]


def _generate_candidate_slots(
    window: Tuple[float, float], step: float
) -> List[float]:
    """Generate slot center hours within the window at the given step."""
    slots = []
    t = window[0]
    while t <= window[1] + 1e-9:
        slots.append(round(t, 4))
        t += step
    return slots


def _build_slot_capacity_lookup(
    time_slots: List[float],
    capacities: List[float],
    candidate_slots: List[float],
) -> Dict[float, float]:
    """
    Map each candidate stagger slot to a capacity value.

    Sim time_slots are 15-min granular; candidate stagger slots are 30-min
    spaced. For each candidate, sum the sim slot capacities within ±15 min
    (the 30-min window centered on the candidate).
    """
    lookup: Dict[float, float] = {}
    for cs in candidate_slots:
        total = 0.0
        for ts, cap in zip(time_slots, capacities):
            if abs(ts - cs) <= _HALF_SLOT_TOLERANCE:
                total += cap
        lookup[cs] = total
    return lookup


def format_hour_to_time(hour: float) -> str:
    """Convert decimal hour to HH:MM string (e.g. 8.5 -> '08:30')."""
    h = int(hour)
    m = int(round((hour - h) * 60))
    return f"{h:02d}:{m:02d}"


def _validate_inputs(
    companies: List[dict],
    time_slots: List[float],
    capacities: List[float],
    window: Tuple[float, float],
) -> None:
    """Validate stagger optimizer inputs."""
    if not companies:
        raise ValueError("Companies list cannot be empty")
    if len(time_slots) != len(capacities):
        raise ValueError(
            f"time_slots length ({len(time_slots)}) must match "
            f"capacities length ({len(capacities)})"
        )
    if not time_slots:
        raise ValueError("time_slots cannot be empty")
    if window[0] >= window[1]:
        raise ValueError(
            f"Window start ({window[0]}) must be before end ({window[1]})"
        )
    for company in companies:
        for key in ("code", "total_staff", "default_start_hour"):
            if key not in company:
                raise ValueError(
                    f"Company dict missing required key '{key}': {company}"
                )
