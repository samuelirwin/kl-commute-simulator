"""
Staggered working hours optimizer.

Uses SciPy's SLSQP (Sequential Least Squares Programming) to find optimal
start times for each company that minimize the peak traffic demand across
all time slots. The optimizer shifts company start times within a configurable
window while preserving ordering preferences.
"""

import logging
from typing import Dict, List, Tuple

import numpy as np
from scipy.optimize import minimize

from simulation.engine.demand import generate_demand_profile

logger = logging.getLogger("simulation")

# Default departure offset: staff leave ~45 min before start time
_DEPARTURE_OFFSET_HOURS = 0.75

# Default standard deviation for the Gaussian departure distribution
_DEFAULT_STD_DEV = 0.5


def optimize_stagger(
    companies: List[dict],
    time_slots: List[float],
    capacities: List[float],
    window: Tuple[float, float] = (7.0, 10.5),
) -> Dict[str, float]:
    """
    Optimize company start times to minimize peak demand across time slots.

    The objective function sums the squared excess demand over capacity for
    all time slots (a proxy for total system delay). Each company's start
    hour is bounded within the window.

    Args:
        companies: List of dicts with keys:
            - code: str (company identifier)
            - total_staff: int (number of commuters)
            - default_start_hour: float (current start time in hours,
              e.g. 8.0 for 8:00 AM)
        time_slots: List of float hours for simulation intervals
            (e.g. [6.0, 6.25, 6.5, ...]).
        capacities: List of float capacity values per time slot. Must have
            the same length as time_slots.
        window: Tuple (earliest_start, latest_start) in hours.
            Default (7.0, 10.5) = 7:00 AM to 10:30 AM.

    Returns:
        Dict mapping company_code -> optimized start_hour (float).

    Raises:
        ValueError: If companies is empty, time_slots/capacities length
            mismatch, or window is invalid.
    """
    _validate_inputs(companies, time_slots, capacities, window)

    num_companies = len(companies)
    slots_array = np.array(time_slots, dtype=np.float64)
    cap_array = np.array(capacities, dtype=np.float64)

    # Initial guess: use default start hours
    x0 = np.array(
        [c["default_start_hour"] for c in companies], dtype=np.float64
    )

    # Bounds: each company start hour within the allowed window
    bounds = [(window[0], window[1])] * num_companies

    logger.info(
        "Starting stagger optimization: %d companies, %d time slots, "
        "window=%.1f-%.1fh",
        num_companies,
        len(time_slots),
        window[0],
        window[1],
    )

    def objective(start_hours: np.ndarray) -> float:
        """Minimize total squared excess demand over capacity."""
        total_demand = np.zeros(len(time_slots), dtype=np.float64)

        for i, company in enumerate(companies):
            mean_departure = start_hours[i] - _DEPARTURE_OFFSET_HOURS
            std_dev = company.get("std_dev", _DEFAULT_STD_DEV)
            profile = generate_demand_profile(
                time_slots, mean_departure, std_dev, company["total_staff"]
            )
            total_demand += profile.astype(np.float64)

        # Penalize demand exceeding capacity at any slot
        excess = np.maximum(total_demand - cap_array, 0.0)
        # Also penalize high peaks even below capacity (spread preference)
        peak_penalty = np.max(total_demand) * 0.01
        return float(np.sum(excess ** 2) + peak_penalty)

    result = minimize(
        objective,
        x0,
        method="SLSQP",
        bounds=bounds,
        options={"maxiter": 200, "ftol": 1e-8, "disp": False},
    )

    if not result.success:
        logger.warning(
            "Stagger optimizer did not converge: %s. Using best found solution.",
            result.message,
        )
    else:
        logger.info(
            "Stagger optimization converged in %d iterations, "
            "objective=%.4f",
            result.nit,
            result.fun,
        )

    # Build result mapping
    optimized = {}
    for i, company in enumerate(companies):
        optimized_hour = round(float(result.x[i]), 2)
        shift_minutes = (optimized_hour - company["default_start_hour"]) * 60

        optimized[company["code"]] = optimized_hour

        logger.info(
            "Company %s: default=%.2fh -> optimized=%.2fh (shift %+.0f min)",
            company["code"],
            company["default_start_hour"],
            optimized_hour,
            shift_minutes,
        )

    return optimized


def format_hour_to_time(hour: float) -> str:
    """
    Convert a decimal hour to HH:MM string.

    Args:
        hour: Time as decimal hours (e.g. 8.5 -> "08:30").

    Returns:
        Formatted time string.
    """
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
