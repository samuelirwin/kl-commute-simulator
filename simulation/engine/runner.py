"""
Simulation orchestrator.

Pipeline that loads data from Django models, runs all optimization algorithms,
executes before/after traffic simulations, calculates CO2 impact, and saves
results back to the database.

Models are imported at function level to avoid circular imports during
Django app initialization.
"""

import logging
from datetime import time as dt_time
from typing import Dict, List, Tuple

from django.utils import timezone

from simulation.engine.carpool import match_carpools
from simulation.engine.co2 import calculate_co2_reduction
from simulation.engine.stagger import optimize_stagger
from simulation.engine.traffic_sim import generate_time_slots, run_traffic_simulation
from simulation.engine.wfh import plan_wfh_rotation

logger = logging.getLogger("simulation")


def execute_simulation(run_id: int) -> None:
    """
    Execute the full MyCommute simulation pipeline for a given run.

    Pipeline steps:
    1. Load configuration and reference data from Django models.
    2. Run stagger optimizer (if enabled).
    3. Generate WFH rotation plan (if enabled).
    4. Match carpool groups (if enabled).
    5. Run "before" traffic simulation (status quo, no optimizations).
    6. Run "after" traffic simulation (with all enabled measures).
    7. Calculate CO2 reduction.
    8. Save all results back to database models.

    Args:
        run_id: Primary key of the SimulationRun to execute.

    Raises:
        SimulationRun.DoesNotExist: If the run_id is not found.
        Exception: Any unhandled error during simulation; the run
            status will be set to "ERR" with details logged.
    """
    # Import models at function level to avoid circular imports
    from simulation.models import (
        CompanySimResult,
        CorridorTimeSlice,
        SimulationRun,
    )

    run = SimulationRun.objects.get(pk=run_id)

    logger.info("Starting simulation run #%d: '%s'", run_id, run.name)
    _update_status(run, "RUN")

    try:
        # Step 1: Load reference data
        corridors, companies, staff_list, modal_split, zone_distances = (
            _load_reference_data()
        )

        time_slots = generate_time_slots()
        day_of_week = 1  # Default to Tuesday for representative weekday

        logger.info(
            "Data loaded: %d corridors, %d companies, %d staff, %d modes",
            len(corridors),
            len(companies),
            len(staff_list),
            len(modal_split),
        )

        # Step 2: Stagger optimization
        stagger_plan: Dict[str, float] = {}
        if run.enable_stagger:
            stagger_plan = _run_stagger_optimization(
                companies, time_slots, corridors, run
            )

        # Step 3: WFH rotation
        wfh_plan: Dict[str, List[int]] = {}
        if run.enable_wfh:
            wfh_plan = _run_wfh_planning(companies, run)

        # Step 4: Carpool matching
        carpool_groups: List[dict] = []
        if run.enable_carpool:
            carpool_groups = _run_carpool_matching(
                staff_list, zone_distances, run
            )

        # Step 5: "Before" simulation (status quo)
        logger.info("Running 'before' scenario simulation...")
        before_result = run_traffic_simulation(
            corridors=corridors,
            companies=companies,
            modal_split=modal_split,
            stagger_plan={},       # No stagger in baseline
            wfh_plan={},           # No WFH in baseline
            carpool_groups=[],     # No carpools in baseline
            day_of_week=day_of_week,
        )

        # Step 6: "After" simulation (with optimizations)
        logger.info("Running 'after' scenario simulation...")
        after_result = run_traffic_simulation(
            corridors=corridors,
            companies=companies,
            modal_split=modal_split,
            stagger_plan=stagger_plan,
            wfh_plan=wfh_plan,
            carpool_groups=carpool_groups,
            day_of_week=day_of_week,
        )

        # Step 7: CO2 calculation
        vehicles_removed = (
            before_result["summary"]["peak_vehicles"]
            - after_result["summary"]["peak_vehicles"]
        )
        vehicles_removed = max(vehicles_removed, 0)

        avg_distance = _compute_avg_commute_distance(corridors)

        congestion_before = before_result["summary"]["peak_congestion"]
        congestion_after = after_result["summary"]["peak_congestion"]
        congestion_reduction = 0.0
        if congestion_before > 0:
            congestion_reduction = (
                (congestion_before - congestion_after) / congestion_before
            ) * 100

        co2_result = calculate_co2_reduction(
            vehicles_removed=vehicles_removed,
            avg_distance_km=avg_distance,
            congestion_reduction_pct=max(congestion_reduction, 0),
            modal_split=modal_split,
        )

        # Step 8: Save results
        _save_corridor_time_slices(
            run, before_result["corridor_data"], "before"
        )
        _save_corridor_time_slices(
            run, after_result["corridor_data"], "after"
        )
        _save_company_results(
            run, companies, stagger_plan, wfh_plan, carpool_groups, day_of_week
        )
        _save_carpool_groups_to_db(run, carpool_groups)

        # Update run aggregate results
        run.peak_congestion_before = before_result["summary"]["peak_congestion"]
        run.peak_congestion_after = after_result["summary"]["peak_congestion"]
        run.avg_commute_before = before_result["summary"]["avg_travel_time_min"]
        run.avg_commute_after = after_result["summary"]["avg_travel_time_min"]
        run.peak_vehicles_before = before_result["summary"]["peak_vehicles"]
        run.peak_vehicles_after = after_result["summary"]["peak_vehicles"]
        run.co2_saved_tonnes = co2_result["total_tonnes"]
        run.total_carpool_groups = len(carpool_groups)
        run.total_wfh_today = _count_wfh_today(companies, wfh_plan, day_of_week)
        run.completed_at = timezone.now()

        _update_status(run, "CMP")

        logger.info(
            "Simulation run #%d completed: congestion %.4f -> %.4f, "
            "commute %.1f -> %.1f min, CO2 saved %.4f tonnes",
            run_id,
            run.peak_congestion_before,
            run.peak_congestion_after,
            run.avg_commute_before,
            run.avg_commute_after,
            run.co2_saved_tonnes,
        )

    except Exception:
        logger.exception(
            "Simulation run #%d failed with unhandled error", run_id
        )
        _update_status(run, "ERR")
        raise


def _update_status(run, status: str) -> None:
    """Update run status and save."""
    run.status = status
    run.save(update_fields=["status"])
    logger.info("Run #%d status updated to '%s'", run.pk, status)


def _load_reference_data() -> tuple:
    """
    Load all reference data from Django models.

    Returns:
        Tuple of (corridors, companies, staff_list, modal_split, zone_distances)
        all as plain dicts/lists for algorithm consumption.
    """
    from company.models import Company, StaffMember
    from core.models import Corridor, ModalSplit, Zone

    # Load corridors
    corridors = []
    for c in Corridor.objects.select_related("zone_from", "zone_to").all():
        corridors.append({
            "code": c.code,
            "zone_from": c.zone_from.code,
            "zone_to": c.zone_to.code,
            "distance_km": c.distance_km,
            "free_flow_speed_kmh": c.free_flow_speed_kmh,
            "capacity_vph": c.capacity_vph,
            "bpr_alpha": c.bpr_alpha,
            "bpr_beta": c.bpr_beta,
        })

    # Load companies
    companies = []
    for comp in Company.objects.select_related("office_zone").all():
        companies.append({
            "code": comp.code,
            "total_staff": comp.total_staff,
            "office_zone": comp.office_zone.code,
            "start_hour": comp.default_start_time.hour + comp.default_start_time.minute / 60.0,
            "default_start_hour": comp.default_start_time.hour + comp.default_start_time.minute / 60.0,
            "sector": comp.sector,
            "wfh_days_per_week": comp.wfh_days_per_week,
        })

    # Load staff members
    staff_list = []
    for s in StaffMember.objects.select_related(
        "company", "company__office_zone", "home_zone"
    ).all():
        staff_list.append({
            "id": s.employee_id,
            "name": s.name,
            "home_zone": s.home_zone.code,
            "office_zone": s.company.office_zone.code,
            "has_vehicle": s.has_vehicle,
            "willing_to_carpool": s.willing_to_carpool,
            "carpool_seats": s.carpool_seats,
            "departure_hour": (
                s.company.default_start_time.hour
                + s.company.default_start_time.minute / 60.0
                - 0.75  # Default departure offset
            ),
        })

    # Load modal split
    modal_split = {}
    for ms in ModalSplit.objects.all():
        modal_split[ms.mode] = {
            "share_pct": ms.share_pct,
            "avg_occupancy": ms.avg_occupancy,
        }

    # Compute zone distances (Euclidean approximation from lat/long)
    zone_distances = _compute_zone_distances()

    return corridors, companies, staff_list, modal_split, zone_distances


def _compute_zone_distances() -> Dict[tuple, float]:
    """
    Compute approximate distances between all zone pairs.

    Uses the Haversine-like flat-earth approximation suitable for
    Klang Valley's small geographic extent (~50km radius).
    """
    from core.models import Zone

    zones = list(Zone.objects.all())
    distances = {}

    for i, z1 in enumerate(zones):
        for z2 in zones[i + 1:]:
            # Flat-earth approximation (adequate for KL scale)
            dlat = (z2.latitude - z1.latitude) * 111.0  # ~111 km per degree
            dlon = (z2.longitude - z1.longitude) * 111.0 * 0.87  # cos(3.1 degrees)
            dist = (dlat ** 2 + dlon ** 2) ** 0.5
            # Fall back to a reasonable default if coordinates are zero
            if dist < 0.1:
                dist = 15.0  # Default 15 km for unknown pairs
            distances[(z1.code, z2.code)] = round(dist, 2)

    logger.debug(
        "Computed %d zone-pair distances", len(distances)
    )

    return distances


def _run_stagger_optimization(
    companies: List[dict],
    time_slots: List[float],
    corridors: List[dict],
    run,
) -> Dict[str, float]:
    """Run the stagger optimizer with run parameters."""
    # Build capacity array (sum of all corridor capacities per slot)
    total_capacity_per_hour = sum(c["capacity_vph"] for c in corridors)
    slot_duration = 0.25  # 15-minute slots
    capacities = [total_capacity_per_hour * slot_duration] * len(time_slots)

    # Parse stagger window from run configuration
    window_start = 7.0
    window_end = 10.5
    if run.stagger_window_start:
        window_start = (
            run.stagger_window_start.hour
            + run.stagger_window_start.minute / 60.0
        )
    if run.stagger_window_end:
        window_end = (
            run.stagger_window_end.hour
            + run.stagger_window_end.minute / 60.0
        )

    logger.info(
        "Running stagger optimizer: window=%.1f-%.1fh", window_start, window_end
    )

    return optimize_stagger(
        companies=companies,
        time_slots=time_slots,
        capacities=capacities,
        window=(window_start, window_end),
    )


def _run_wfh_planning(
    companies: List[dict], run
) -> Dict[str, List[int]]:
    """Run the WFH rotation planner with run parameters."""
    logger.info(
        "Running WFH planner: sector_cap=%d%%", run.wfh_sector_cap_pct
    )

    return plan_wfh_rotation(
        companies=companies,
        sector_cap_pct=run.wfh_sector_cap_pct,
    )


def _run_carpool_matching(
    staff_list: List[dict],
    zone_distances: Dict[tuple, float],
    run,
) -> List[dict]:
    """Run the carpool matcher with run parameters."""
    logger.info(
        "Running carpool matcher: max_detour=%.1f km",
        run.carpool_max_detour_km,
    )

    return match_carpools(
        staff_list=staff_list,
        zone_distances=zone_distances,
        max_detour_km=run.carpool_max_detour_km,
    )


def _save_corridor_time_slices(
    run, corridor_data: List[dict], scenario: str
) -> None:
    """Bulk-create CorridorTimeSlice records for a scenario."""
    from core.models import Corridor
    from simulation.models import CorridorTimeSlice

    # Build code -> Corridor object lookup
    corridor_lookup = {c.code: c for c in Corridor.objects.all()}

    records = []
    for entry in corridor_data:
        corridor_obj = corridor_lookup.get(entry["corridor_code"])
        if not corridor_obj:
            logger.warning(
                "Corridor '%s' not found in database, skipping time slice",
                entry["corridor_code"],
            )
            continue

        records.append(CorridorTimeSlice(
            simulation_run=run,
            corridor=corridor_obj,
            time_slot=entry["time_slot"],
            scenario=scenario,
            volume=entry["volume_pce"],
            volume_car=entry["volume_car"],
            volume_motorcycle=entry["volume_motorcycle"],
            capacity_ratio=entry["capacity_ratio"],
            travel_time_min=entry["travel_time_min"],
            speed_kmh=entry["speed_kmh"],
            congestion_level=entry["congestion_level"],
        ))

    CorridorTimeSlice.objects.filter(
        simulation_run=run, scenario=scenario
    ).delete()

    CorridorTimeSlice.objects.bulk_create(records, batch_size=500)

    logger.info(
        "Saved %d corridor time slices for scenario '%s'",
        len(records),
        scenario,
    )


def _save_company_results(
    run,
    companies: List[dict],
    stagger_plan: Dict[str, float],
    wfh_plan: Dict[str, List[int]],
    carpool_groups: List[dict],
    day_of_week: int,
) -> None:
    """Save per-company simulation results."""
    from company.models import Company
    from simulation.models import CompanySimResult

    company_lookup = {c.code: c for c in Company.objects.all()}

    # Count carpool participants per company (via staff office zones)
    carpool_counts: Dict[str, int] = {}
    for group in carpool_groups:
        passenger_count = len(group.get("passenger_ids", []))
        # Attribute to the hub zone as approximation
        hub = group.get("hub_zone", "")
        carpool_counts[hub] = carpool_counts.get(hub, 0) + passenger_count + 1

    CompanySimResult.objects.filter(simulation_run=run).delete()

    records = []
    for company_data in companies:
        code = company_data["code"]
        company_obj = company_lookup.get(code)
        if not company_obj:
            logger.warning(
                "Company '%s' not found in database, skipping", code
            )
            continue

        # Assigned start time (from stagger plan or default)
        start_hour = stagger_plan.get(code, company_data["start_hour"])
        h = int(start_hour)
        m = int(round((start_hour - h) * 60))
        assigned_time = dt_time(h, m)

        # WFH count for today
        is_wfh_today = day_of_week in wfh_plan.get(code, [])
        wfh_count = (
            int(company_data["total_staff"] * 0.2) if is_wfh_today else 0
        )

        staff_before = company_data["total_staff"]
        staff_after = staff_before - wfh_count

        records.append(CompanySimResult(
            simulation_run=run,
            company=company_obj,
            assigned_start_time=assigned_time,
            staff_on_road_before=staff_before,
            staff_on_road_after=staff_after,
            wfh_count=wfh_count,
            carpool_count=carpool_counts.get(
                company_data.get("office_zone", ""), 0
            ),
            load_contribution=round(
                staff_after / max(sum(c["total_staff"] for c in companies), 1),
                4,
            ),
        ))

    CompanySimResult.objects.bulk_create(records, batch_size=100)

    logger.info(
        "Saved %d company simulation results", len(records)
    )


def _save_carpool_groups_to_db(run, carpool_groups: List[dict]) -> None:
    """Save carpool groups and memberships to the database."""
    from core.models import CarpoolHub
    from staff.models import CarpoolGroup, CarpoolMembership
    from company.models import StaffMember

    # Clear existing groups for this run
    CarpoolGroup.objects.filter(simulation_run=run).delete()

    if not carpool_groups:
        logger.info("No carpool groups to save")
        return

    # Build lookups
    hub_lookup = {}
    for hub in CarpoolHub.objects.select_related("zone").all():
        hub_lookup[hub.zone.code] = hub

    staff_lookup = {s.employee_id: s for s in StaffMember.objects.all()}

    saved_count = 0
    for group_data in carpool_groups:
        hub = hub_lookup.get(group_data.get("hub_zone"))

        departure_hour = group_data.get("departure_time", 7.5)
        h = int(departure_hour)
        m = int(round((departure_hour - h) * 60))

        db_group = CarpoolGroup.objects.create(
            name=group_data["name"],
            hub=hub,
            route_description=group_data.get("route", ""),
            departure_time=dt_time(h, m),
            max_seats=1 + len(group_data.get("passenger_ids", [])),
            simulation_run=run,
        )

        # Add driver membership
        driver_staff = staff_lookup.get(str(group_data.get("driver_id", "")))
        if driver_staff:
            CarpoolMembership.objects.create(
                staff=driver_staff,
                group=db_group,
                role="DRV",
            )

        # Add passenger memberships
        for pid in group_data.get("passenger_ids", []):
            passenger_staff = staff_lookup.get(str(pid))
            if passenger_staff:
                CarpoolMembership.objects.create(
                    staff=passenger_staff,
                    group=db_group,
                    role="PSG",
                )

        saved_count += 1

    logger.info("Saved %d carpool groups to database", saved_count)


def _count_wfh_today(
    companies: List[dict],
    wfh_plan: Dict[str, List[int]],
    day_of_week: int,
) -> int:
    """Count total staff working from home on the given day."""
    total = 0
    for company in companies:
        code = company["code"]
        if day_of_week in wfh_plan.get(code, []):
            total += int(company["total_staff"] * 0.2)
    return total


def _compute_avg_commute_distance(corridors: List[dict]) -> float:
    """Compute average corridor distance as a proxy for average commute."""
    if not corridors:
        return 20.0  # Default 20 km for KL
    total = sum(c["distance_km"] for c in corridors)
    return total / len(corridors)
