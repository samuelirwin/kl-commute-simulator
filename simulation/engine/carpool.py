"""
Carpool matching engine.

Clusters willing-to-carpool staff by destination (office) zone, then
greedily matches drivers to nearby riders within an origin proximity
threshold. Each carpool group has exactly one driver and up to N-1
passengers (where N = driver's carpool_seats).

The matcher prioritizes groups by:
1. Destination zone (staff going to the same office zone)
2. Origin proximity (riders within max_detour_km of the driver's home zone)
3. Departure time compatibility (within a 30-min window)
"""

import logging
from collections import defaultdict
from typing import Dict, List, Tuple

logger = logging.getLogger("simulation")

# Maximum departure time difference (hours) for compatible carpooling
_MAX_DEPARTURE_DIFF_HOURS = 0.5

# Group naming counter prefix
_GROUP_PREFIX = "CP"


def match_carpools(
    staff_list: List[dict],
    zone_distances: Dict[Tuple[str, str], float],
    max_detour_km: float = 5.0,
) -> List[dict]:
    """
    Match willing-to-carpool staff into carpool groups.

    Algorithm:
    1. Filter staff to only willing_to_carpool=True.
    2. Cluster by office_zone (destination).
    3. Within each cluster, identify drivers (has_vehicle=True, carpool_seats>0).
    4. For each driver, greedily assign nearest compatible riders.

    Args:
        staff_list: List of dicts with keys:
            - id: unique identifier (str or int)
            - name: staff name
            - home_zone: origin zone code
            - office_zone: destination zone code
            - has_vehicle: bool
            - willing_to_carpool: bool
            - carpool_seats: int (total seats including driver)
            - departure_hour: float (e.g. 7.25 for 7:15 AM)
        zone_distances: Dict mapping (zone_a, zone_b) -> distance in km.
            Should contain entries for relevant zone pairs.
        max_detour_km: Maximum extra distance a driver would travel to
            pick up a rider. Default 5.0 km.

    Returns:
        List of group dicts with keys:
            - name: str (group identifier, e.g. "CP-001")
            - hub_zone: str (common origin zone, driver's home)
            - route: str (description of zones in route)
            - departure_time: float (driver's departure hour)
            - driver_id: str or int
            - passenger_ids: list of str or int

    Raises:
        ValueError: If max_detour_km < 0.
    """
    if max_detour_km < 0:
        raise ValueError(
            f"max_detour_km must be non-negative, got {max_detour_km}"
        )

    # Step 1: Filter willing participants
    willing = [s for s in staff_list if s.get("willing_to_carpool", False)]
    logger.info(
        "Carpool matching: %d willing out of %d total staff",
        len(willing),
        len(staff_list),
    )

    if not willing:
        logger.info("No willing carpool participants found")
        return []

    # Step 2: Cluster by destination zone
    destination_clusters = _cluster_by_destination(willing)

    # Step 3 & 4: Match within each cluster
    all_groups: List[dict] = []
    group_counter = 0

    for office_zone, members in destination_clusters.items():
        drivers, riders = _separate_drivers_riders(members)

        logger.debug(
            "Zone %s: %d drivers, %d riders",
            office_zone,
            len(drivers),
            len(riders),
        )

        # Sort drivers by departure_hour for deterministic results
        drivers.sort(key=lambda d: d["departure_hour"])
        unmatched_riders = list(riders)

        for driver in drivers:
            group_counter += 1
            group_name = f"{_GROUP_PREFIX}-{group_counter:03d}"

            matched_passengers = _find_compatible_riders(
                driver=driver,
                available_riders=unmatched_riders,
                zone_distances=zone_distances,
                max_detour_km=max_detour_km,
            )

            # Remove matched riders from the pool
            matched_ids = {p["id"] for p in matched_passengers}
            unmatched_riders = [
                r for r in unmatched_riders if r["id"] not in matched_ids
            ]

            group = _build_group(
                group_name=group_name,
                driver=driver,
                passengers=matched_passengers,
            )
            all_groups.append(group)

            logger.debug(
                "Group %s: driver=%s, passengers=%d, hub=%s",
                group_name,
                driver["name"],
                len(matched_passengers),
                driver["home_zone"],
            )

        # Unmatched riders with vehicles can form single-driver groups
        for rider in unmatched_riders:
            if rider.get("has_vehicle", False) and rider.get("carpool_seats", 0) > 0:
                group_counter += 1
                group_name = f"{_GROUP_PREFIX}-{group_counter:03d}"
                group = _build_group(
                    group_name=group_name,
                    driver=rider,
                    passengers=[],
                )
                all_groups.append(group)

    logger.info(
        "Carpool matching complete: %d groups formed, %d total participants",
        len(all_groups),
        sum(1 + len(g["passenger_ids"]) for g in all_groups),
    )

    return all_groups


def _cluster_by_destination(
    staff: List[dict],
) -> Dict[str, List[dict]]:
    """Group staff by their office_zone."""
    clusters: Dict[str, List[dict]] = defaultdict(list)
    for person in staff:
        clusters[person["office_zone"]].append(person)
    return clusters


def _separate_drivers_riders(
    members: List[dict],
) -> Tuple[List[dict], List[dict]]:
    """
    Split cluster members into drivers and riders.

    Drivers: has_vehicle=True and carpool_seats > 0.
    Riders: everyone else (including vehicle owners with 0 seats offered).
    """
    drivers = [
        m for m in members
        if m.get("has_vehicle", False) and m.get("carpool_seats", 0) > 0
    ]
    rider_ids = {d["id"] for d in drivers}
    riders = [m for m in members if m["id"] not in rider_ids]
    return drivers, riders


def _find_compatible_riders(
    driver: dict,
    available_riders: List[dict],
    zone_distances: Dict[Tuple[str, str], float],
    max_detour_km: float,
) -> List[dict]:
    """
    Find riders compatible with the given driver.

    Compatibility criteria:
    - Same office_zone (guaranteed by clustering)
    - Home zone within max_detour_km of driver's home zone
    - Departure hour within _MAX_DEPARTURE_DIFF_HOURS
    """
    max_passengers = max(driver.get("carpool_seats", 1) - 1, 0)
    if max_passengers == 0:
        return []

    driver_home = driver["home_zone"]
    driver_departure = driver["departure_hour"]

    # Score riders by proximity (closer = better)
    scored_riders = []
    for rider in available_riders:
        # Check departure time compatibility
        time_diff = abs(rider["departure_hour"] - driver_departure)
        if time_diff > _MAX_DEPARTURE_DIFF_HOURS:
            continue

        # Check zone proximity
        distance = _get_zone_distance(
            zone_distances, driver_home, rider["home_zone"]
        )
        if distance <= max_detour_km:
            scored_riders.append((distance, rider))

    # Sort by distance (nearest first)
    scored_riders.sort(key=lambda x: x[0])

    # Take up to max_passengers
    return [rider for _, rider in scored_riders[:max_passengers]]


def _get_zone_distance(
    zone_distances: Dict[Tuple[str, str], float],
    zone_a: str,
    zone_b: str,
) -> float:
    """
    Look up distance between two zones (symmetric).

    Returns a large number if the pair is not in the distance dict,
    effectively excluding unknown pairs from matching.
    """
    if zone_a == zone_b:
        return 0.0
    distance = zone_distances.get((zone_a, zone_b))
    if distance is None:
        distance = zone_distances.get((zone_b, zone_a))
    if distance is None:
        return float("inf")
    return distance


def _build_group(
    group_name: str,
    driver: dict,
    passengers: List[dict],
) -> dict:
    """Construct a carpool group dict from driver and passengers."""
    route_zones = [driver["home_zone"]]
    for p in passengers:
        if p["home_zone"] not in route_zones:
            route_zones.append(p["home_zone"])
    route_zones.append(driver["office_zone"])

    return {
        "name": group_name,
        "hub_zone": driver["home_zone"],
        "route": " -> ".join(route_zones),
        "departure_time": driver["departure_hour"],
        "driver_id": driver["id"],
        "passenger_ids": [p["id"] for p in passengers],
    }
