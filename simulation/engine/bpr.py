"""
BPR (Bureau of Public Roads) travel time function.

Implements the standard FHWA volume-delay function used by transport planning
agencies worldwide. Given free-flow travel time, traffic volume, and road
capacity, returns the congested travel time.

Reference: Highway Capacity Manual (HCM), FHWA BPR curve formulation.
"""

import logging
logger = logging.getLogger("simulation")


def travel_time(
    free_flow_time: float,
    volume: float,
    capacity: float,
    alpha: float = 0.15,
    beta: float = 4.0,
) -> float:
    """
    Calculate congested travel time using the BPR volume-delay function.

    Formula: t = t0 * (1 + alpha * (V/C)^beta)

    Args:
        free_flow_time: Free-flow travel time in minutes (t0). Must be > 0.
        volume: Traffic volume (vehicles or PCE) for the time period.
        capacity: Road capacity (vehicles or PCE) for the same time period.
            Must be > 0.
        alpha: BPR alpha calibration parameter. FHWA default is 0.15.
        beta: BPR beta calibration parameter. FHWA default is 4.0.

    Returns:
        Congested travel time in the same unit as free_flow_time (minutes).

    Raises:
        ValueError: If free_flow_time <= 0, capacity <= 0, volume < 0,
            alpha < 0, or beta < 0.
    """
    _validate_inputs(free_flow_time, volume, capacity, alpha, beta)

    vc_ratio = volume / capacity
    delay_factor = 1.0 + alpha * (vc_ratio ** beta)
    result = free_flow_time * delay_factor

    logger.debug(
        "BPR calculation: t0=%.2f, V/C=%.4f, alpha=%.3f, beta=%.2f -> t=%.2f min",
        free_flow_time,
        vc_ratio,
        alpha,
        beta,
        result,
    )

    return result


def congestion_index(volume: float, capacity: float) -> float:
    """
    Calculate a normalized congestion index from 0.0 (free flow) to 1.0+ (over capacity).

    This is a simple V/C ratio bounded at zero. Values above 1.0 indicate
    demand exceeding capacity (oversaturated conditions).

    Args:
        volume: Traffic volume for the period.
        capacity: Road capacity for the period. Must be > 0.

    Returns:
        Congestion index as a float (0.0 = empty, 1.0 = at capacity).

    Raises:
        ValueError: If capacity <= 0 or volume < 0.
    """
    if capacity <= 0:
        raise ValueError(f"Capacity must be positive, got {capacity}")
    if volume < 0:
        raise ValueError(f"Volume cannot be negative, got {volume}")

    index = volume / capacity

    logger.debug(
        "Congestion index: volume=%.0f, capacity=%.0f -> index=%.4f",
        volume,
        capacity,
        index,
    )

    return index


def _validate_inputs(
    free_flow_time: float,
    volume: float,
    capacity: float,
    alpha: float,
    beta: float,
) -> None:
    """Validate BPR function inputs and raise ValueError on invalid data."""
    if free_flow_time <= 0:
        raise ValueError(
            f"Free-flow time must be positive, got {free_flow_time}"
        )
    if volume < 0:
        raise ValueError(f"Volume cannot be negative, got {volume}")
    if capacity <= 0:
        raise ValueError(f"Capacity must be positive, got {capacity}")
    if alpha < 0:
        raise ValueError(f"Alpha must be non-negative, got {alpha}")
    if beta < 0:
        raise ValueError(f"Beta must be non-negative, got {beta}")
