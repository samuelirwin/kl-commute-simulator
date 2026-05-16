"""
Origin-Destination path routing.

Builds an undirected weighted graph from the corridor list and computes
shortest paths between zone pairs using Dijkstra. Each path is returned
as the ordered list of corridor codes traversed.

Why this exists
---------------
The traffic simulator originally assigned demand to corridors only by
matching `corridor.zone_to == office_zone`. That ignored through-traffic
(staff passing through a corridor on the way somewhere else) and over-
loaded direct-link corridors. With path routing, a trip from Subang to
KLCC correctly loads FEDHWY (Subang→PJ→KLSNTRL), Bangsar-Sentral, and
the inner-city link rather than just the corridor terminating at KLCC.
"""

import heapq
import logging
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger("simulation")


def build_corridor_graph(
    corridors: List[dict],
) -> Dict[str, List[Tuple[str, float, str]]]:
    """
    Build an undirected adjacency list from corridor definitions.

    Args:
        corridors: List of dicts with keys `code`, `zone_from`, `zone_to`,
            `distance_km`.

    Returns:
        Dict mapping zone_code -> list of (neighbor_zone, distance_km,
        corridor_code) tuples. Edges appear in both directions since
        corridors carry traffic both ways.
    """
    adj: Dict[str, List[Tuple[str, float, str]]] = defaultdict(list)
    for c in corridors:
        a, b = c["zone_from"], c["zone_to"]
        d = float(c["distance_km"])
        code = c["code"]
        adj[a].append((b, d, code))
        adj[b].append((a, d, code))
    return adj


def shortest_path_corridors(
    graph: Dict[str, List[Tuple[str, float, str]]],
    source: str,
    target: str,
) -> Optional[List[str]]:
    """
    Return the ordered list of corridor codes on the shortest distance
    path from source to target zone, or None if unreachable.

    Same source and target returns an empty list — a person whose home
    and office zone are the same uses zero corridors.
    """
    if source == target:
        return []
    if source not in graph or target not in graph:
        return None

    # (cumulative_distance, current_zone, path_of_corridor_codes)
    queue: List[Tuple[float, str, Tuple[str, ...]]] = [(0.0, source, ())]
    visited: set[str] = set()

    while queue:
        cost, node, path = heapq.heappop(queue)
        if node in visited:
            continue
        visited.add(node)
        if node == target:
            return list(path)
        for neighbor, weight, corridor_code in graph[node]:
            if neighbor not in visited:
                heapq.heappush(
                    queue,
                    (cost + weight, neighbor, path + (corridor_code,)),
                )

    return None


def build_path_lookup(
    corridors: List[dict],
    zone_codes: List[str],
) -> Dict[Tuple[str, str], List[str]]:
    """
    Pre-compute shortest-path corridor lists for every ordered zone pair.

    Returns a dict keyed by (source, target). Unreachable pairs are
    logged once and omitted from the result.
    """
    graph = build_corridor_graph(corridors)
    paths: Dict[Tuple[str, str], List[str]] = {}
    unreachable: List[Tuple[str, str]] = []

    for src in zone_codes:
        for dst in zone_codes:
            if src == dst:
                paths[(src, dst)] = []
                continue
            path = shortest_path_corridors(graph, src, dst)
            if path is None:
                unreachable.append((src, dst))
                continue
            paths[(src, dst)] = path

    if unreachable:
        isolated_zones = sorted({z for pair in unreachable for z in pair if z not in graph})
        if isolated_zones:
            logger.warning(
                "Zones with no corridor connections (trips skipped): %s",
                isolated_zones,
            )
        else:
            logger.warning(
                "%d zone pairs unreachable in corridor graph (sample: %s)",
                len(unreachable), unreachable[:3],
            )

    logger.info(
        "Path lookup built: %d corridors, %d zones, %d reachable OD pairs",
        len(corridors), len(zone_codes), len(paths),
    )
    return paths


def compute_od_commute_time_min(
    od_demand: Optional[Dict[Tuple[str, str], np.ndarray]],
    corridor_paths: Dict[Tuple[str, str], List[str]],
    travel_time_matrix: np.ndarray,
    corridor_codes: List[str],
    overhead_min: float = 15.0,
) -> float:
    """
    Volume-weighted door-to-desk commute time across all OD trips.

    For every OD pair we sum the per-corridor BPR travel times along the
    OD's path at the slot the trips depart in, then weight by trip count.
    The flat `overhead_min` captures parking, last-mile walking, and
    elevator/lobby time — not derivable from corridor flows.

    Returns the average door-to-desk one-way commute time in minutes. If
    no OD data is available or no trips exist, returns 0.0.
    """
    if not od_demand:
        return 0.0

    code_to_idx = {code: i for i, code in enumerate(corridor_codes)}

    total_person_minutes = 0.0
    total_person_trips = 0.0

    for (home, office), demand_per_slot in od_demand.items():
        path = corridor_paths.get((home, office))
        if not path:
            continue
        path_indices = [code_to_idx[c] for c in path if c in code_to_idx]
        if not path_indices:
            continue
        # Per-slot trip time = sum of corridor BPR times across the path.
        trip_time_per_slot = travel_time_matrix[path_indices, :].sum(axis=0)
        total_person_minutes += float((trip_time_per_slot * demand_per_slot).sum())
        total_person_trips += float(demand_per_slot.sum())

    if total_person_trips <= 0:
        return 0.0
    return total_person_minutes / total_person_trips + overhead_min
