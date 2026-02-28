"""
Work-From-Home (WFH) rotation planner.

Assigns WFH days to companies such that the daily on-road population is
balanced across the workweek. Enforces a sector cap to prevent too many
companies in the same sector from being off-road on the same day (important
for sectors like banking or government where inter-company coordination
matters).
"""

import logging
from collections import defaultdict
from typing import Dict, List

logger = logging.getLogger("simulation")

# Workweek days: 0=Monday through 4=Friday
_WEEKDAYS = list(range(5))
_DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]


def plan_wfh_rotation(
    companies: List[dict],
    sector_cap_pct: int = 40,
) -> Dict[str, List[int]]:
    """
    Assign WFH days per company to balance daily road load across the week.

    Uses a greedy allocation approach: for each company, pick the day(s)
    with the highest current on-road load (i.e., the day that benefits
    most from removing staff), subject to the sector cap constraint.

    Args:
        companies: List of dicts with keys:
            - code: str (company identifier)
            - sector: str (industry sector for grouping)
            - total_staff: int (total headcount)
            - wfh_days_per_week: int (how many WFH days, 0-5)
        sector_cap_pct: Maximum percentage of any sector's total staff
            that can be WFH on the same day. Default 40%.

    Returns:
        Dict mapping company_code -> list of day indices (0-4).
        Empty list for companies with wfh_days_per_week=0.

    Raises:
        ValueError: If companies is empty or sector_cap_pct not in [0, 100].
    """
    _validate_inputs(companies, sector_cap_pct)

    # Track daily on-road staff load (start with everyone on-road)
    daily_load = _initialize_daily_load(companies)

    # Track sector staff counts per day for cap enforcement
    sector_daily_wfh = _initialize_sector_tracking()

    # Compute sector totals for cap calculation
    sector_totals = _compute_sector_totals(companies)

    # Sort companies by total_staff descending (biggest impact first)
    sorted_companies = sorted(
        companies, key=lambda c: c["total_staff"], reverse=True
    )

    result: Dict[str, List[int]] = {}

    for company in sorted_companies:
        code = company["code"]
        wfh_days = company["wfh_days_per_week"]
        staff = company["total_staff"]
        sector = company["sector"]

        if wfh_days <= 0:
            result[code] = []
            logger.debug("Company %s: no WFH days assigned (policy=0)", code)
            continue

        # Clamp to valid range
        wfh_days = min(wfh_days, 5)

        assigned_days = _assign_days_for_company(
            code=code,
            staff=staff,
            sector=sector,
            wfh_days=wfh_days,
            daily_load=daily_load,
            sector_daily_wfh=sector_daily_wfh,
            sector_totals=sector_totals,
            sector_cap_pct=sector_cap_pct,
        )

        result[code] = assigned_days

        logger.info(
            "Company %s (sector=%s, staff=%d): WFH on %s",
            code,
            sector,
            staff,
            [_DAY_NAMES[d] for d in assigned_days],
        )

    # Log daily summary
    _log_daily_summary(daily_load)

    return result


def _assign_days_for_company(
    code: str,
    staff: int,
    sector: str,
    wfh_days: int,
    daily_load: List[float],
    sector_daily_wfh: Dict[str, List[int]],
    sector_totals: Dict[str, int],
    sector_cap_pct: int,
) -> List[int]:
    """
    Pick the best WFH days for a single company using greedy selection.

    Selects days with the highest current load, subject to the sector cap.
    """
    assigned: List[int] = []
    sector_total = sector_totals[sector]
    max_sector_wfh_per_day = int(sector_total * sector_cap_pct / 100)

    for _ in range(wfh_days):
        # Rank days by current load (highest first) excluding already assigned
        candidates = [d for d in _WEEKDAYS if d not in assigned]

        # Filter by sector cap
        valid_candidates = [
            d for d in candidates
            if (sector_daily_wfh[sector][d] + staff) <= max_sector_wfh_per_day
        ]

        if not valid_candidates:
            # Sector cap prevents further WFH; fall back to best available
            logger.debug(
                "Company %s: sector cap reached for sector '%s', "
                "relaxing constraint for remaining %d day(s)",
                code,
                sector,
                wfh_days - len(assigned),
            )
            valid_candidates = candidates

        if not valid_candidates:
            break

        # Choose the day with the highest load to maximize benefit
        best_day = max(valid_candidates, key=lambda d: daily_load[d])
        assigned.append(best_day)

        # Update tracking
        daily_load[best_day] -= staff
        sector_daily_wfh[sector][best_day] += staff

    return sorted(assigned)


def _initialize_daily_load(companies: List[dict]) -> List[float]:
    """Start with all staff on-road every day."""
    total = sum(c["total_staff"] for c in companies)
    return [float(total)] * 5


def _initialize_sector_tracking() -> Dict[str, List[int]]:
    """Create empty sector WFH tracking dict with defaultdict."""
    return defaultdict(lambda: [0, 0, 0, 0, 0])


def _compute_sector_totals(companies: List[dict]) -> Dict[str, int]:
    """Sum total_staff per sector."""
    totals: Dict[str, int] = defaultdict(int)
    for company in companies:
        totals[company["sector"]] += company["total_staff"]
    return totals


def _log_daily_summary(daily_load: List[float]) -> None:
    """Log the final daily on-road load balance."""
    for day_idx, load in enumerate(daily_load):
        logger.info(
            "Daily load after WFH: %s = %.0f staff on road",
            _DAY_NAMES[day_idx],
            load,
        )

    spread = max(daily_load) - min(daily_load)
    logger.info(
        "WFH load balance spread: %.0f (lower is better)", spread
    )


def _validate_inputs(
    companies: List[dict], sector_cap_pct: int
) -> None:
    """Validate WFH planner inputs."""
    if not companies:
        raise ValueError("Companies list cannot be empty")
    if not (0 <= sector_cap_pct <= 100):
        raise ValueError(
            f"sector_cap_pct must be 0-100, got {sector_cap_pct}"
        )

    for company in companies:
        for key in ("code", "sector", "total_staff", "wfh_days_per_week"):
            if key not in company:
                raise ValueError(
                    f"Company dict missing required key '{key}': {company}"
                )
