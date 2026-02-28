"""
Gaussian demand profile generator.

Models departure time distributions as normal (Gaussian) curves centered on
each company's start time. This reflects the real-world pattern where most
staff depart within a window around their scheduled arrival, with the peak
at approximately (start_time - commute_duration).

Each company produces one Gaussian, and the system overlays all of them to
get the aggregate demand across time slots.
"""

import logging
from typing import List

import numpy as np

logger = logging.getLogger("simulation")


def generate_demand_profile(
    time_slots: List[float],
    mean_hour: float,
    std_dev: float,
    total_demand: int,
) -> np.ndarray:
    """
    Generate a demand distribution across time slots using a Gaussian curve.

    The Gaussian PDF is evaluated at each time slot, then scaled so that the
    sum of all slot demands equals total_demand (rounded to integers).

    Args:
        time_slots: List of float hours representing the center of each
            time interval (e.g. [6.0, 6.25, 6.5, ...] for 15-min slots).
        mean_hour: Center of the Gaussian in hours (e.g. 8.5 for 8:30 AM).
        std_dev: Standard deviation in hours. Typical commute spread is
            0.5-1.0 hours.
        total_demand: Total number of trips to distribute across the slots.

    Returns:
        numpy array of integer demand values, one per time slot, summing
        to approximately total_demand.

    Raises:
        ValueError: If time_slots is empty, std_dev <= 0, or total_demand < 0.
    """
    _validate_inputs(time_slots, std_dev, total_demand)

    slots = np.array(time_slots, dtype=np.float64)

    # Compute Gaussian PDF values (unnormalized)
    raw_weights = _gaussian_pdf(slots, mean_hour, std_dev)

    # Normalize so weights sum to 1.0, then scale by total demand
    weight_sum = raw_weights.sum()
    if weight_sum < 1e-12:
        # All slots are far from the mean; distribute evenly as fallback
        logger.warning(
            "Gaussian weights sum near zero (mean=%.2f, std=%.2f). "
            "Distributing demand evenly across %d slots.",
            mean_hour,
            std_dev,
            len(time_slots),
        )
        demand = np.full(len(time_slots), total_demand / len(time_slots))
    else:
        demand = (raw_weights / weight_sum) * total_demand

    # Round to integers while preserving total
    result = _round_preserving_total(demand, total_demand)

    logger.info(
        "Demand profile generated: mean=%.2fh, std=%.2fh, total=%d, "
        "peak_slot=%.2fh with %d trips, non-zero_slots=%d",
        mean_hour,
        std_dev,
        total_demand,
        time_slots[int(np.argmax(result))],
        int(np.max(result)),
        int(np.count_nonzero(result)),
    )

    return result


def generate_aggregate_profile(
    time_slots: List[float],
    companies: List[dict],
    departure_offset_hours: float = 0.75,
) -> np.ndarray:
    """
    Generate aggregate demand by summing Gaussian profiles for all companies.

    Each company's mean departure time is computed as
    (start_hour - departure_offset_hours), since staff typically depart
    before their office start time.

    Args:
        time_slots: List of float hours for each time interval.
        companies: List of dicts with keys: code, total_staff, start_hour.
            Optional key: std_dev (default 0.5).
        departure_offset_hours: How far before start_hour the average
            departure occurs. Default 0.75 (45 min).

    Returns:
        numpy array of aggregate demand per time slot.
    """
    aggregate = np.zeros(len(time_slots), dtype=np.float64)

    for company in companies:
        mean_hour = company["start_hour"] - departure_offset_hours
        std_dev = company.get("std_dev", 0.5)
        total = company["total_staff"]

        profile = generate_demand_profile(time_slots, mean_hour, std_dev, total)
        aggregate += profile

        logger.debug(
            "Added demand for %s: %d staff, departure_mean=%.2fh",
            company["code"],
            total,
            mean_hour,
        )

    logger.info(
        "Aggregate demand profile: %d companies, total_trips=%d, peak=%d at slot %.2fh",
        len(companies),
        int(aggregate.sum()),
        int(aggregate.max()),
        time_slots[int(np.argmax(aggregate))],
    )

    return aggregate


def _gaussian_pdf(x: np.ndarray, mean: float, std: float) -> np.ndarray:
    """Compute unnormalized Gaussian PDF values (constant factor omitted)."""
    return np.exp(-0.5 * ((x - mean) / std) ** 2)


def _round_preserving_total(
    values: np.ndarray, target_total: int
) -> np.ndarray:
    """
    Round float array to integers while keeping the sum equal to target_total.

    Uses the largest-remainder method to distribute rounding residuals.
    """
    floored = np.floor(values).astype(int)
    remainders = values - floored
    shortfall = target_total - floored.sum()

    # Give +1 to the slots with the largest remainders
    if shortfall > 0:
        indices = np.argsort(remainders)[::-1][:int(shortfall)]
        floored[indices] += 1

    return floored


def _validate_inputs(
    time_slots: List[float], std_dev: float, total_demand: int
) -> None:
    """Validate demand profile inputs."""
    if not time_slots:
        raise ValueError("time_slots cannot be empty")
    if std_dev <= 0:
        raise ValueError(f"std_dev must be positive, got {std_dev}")
    if total_demand < 0:
        raise ValueError(f"total_demand cannot be negative, got {total_demand}")
