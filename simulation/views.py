"""
Simulation API views — JSON endpoints serving dashboard data for a given simulation run.
Each endpoint returns structured JSON for a specific panel (KPIs, map, chart, etc).
"""
import logging
from datetime import time

from django.http import JsonResponse
from django.shortcuts import get_object_or_404

from company.models import Company
from core.models import CarpoolHub, ModalSplit, TransitLine, Zone
from simulation.models import CompanySimResult, CorridorTimeSlice, SimulationRun
from staff.models import CarpoolGroup

logger = logging.getLogger("simulation")


def api_kpis(request, run_id):
    """Return KPI card data for a simulation run."""
    run = get_object_or_404(SimulationRun, pk=run_id)
    logger.info("API kpis requested for run_id=%d", run_id)
    return JsonResponse({
        "run_id": run.id,
        "name": run.name,
        "status": run.status,
        "peak_congestion_before": run.peak_congestion_before or 0,
        "peak_congestion_after": run.peak_congestion_after or 0,
        "avg_commute_before": run.avg_commute_before or 0,
        "avg_commute_after": run.avg_commute_after or 0,
        "peak_vehicles_before": run.peak_vehicles_before or 0,
        "peak_vehicles_after": run.peak_vehicles_after or 0,
        "co2_saved_tonnes": run.co2_saved_tonnes or 0,
        "total_carpool_groups": run.total_carpool_groups or 0,
        "total_wfh_today": run.total_wfh_today or 0,
        "congestion_reduction_pct": run.congestion_reduction_pct,
        "commute_reduction_pct": run.commute_reduction_pct,
        "vehicles_removed": run.vehicles_removed,
    })


def api_map(request, run_id):
    """Return map landmarks, roads with congestion, and carpool hubs."""
    run = get_object_or_404(SimulationRun, pk=run_id)
    logger.info("API map requested for run_id=%d", run_id)

    # Landmarks from zones
    zones = Zone.objects.all()
    landmarks = [
        {
            "name": z.name,
            "code": z.code,
            "x": z.map_x,
            "y": z.map_y,
            "major": z.is_major,
            "icon": z.icon,
        }
        for z in zones
    ]

    # Roads with congestion — aggregate from corridor time slices at peak hour
    from core.models import Corridor
    corridors = Corridor.objects.select_related("zone_from", "zone_to").all()
    roads = []
    for c in corridors:
        # Get peak hour congestion (around 08:00)
        before_slice = CorridorTimeSlice.objects.filter(
            simulation_run=run, corridor=c, scenario="before", time_slot="08:00"
        ).first()
        after_slice = CorridorTimeSlice.objects.filter(
            simulation_run=run, corridor=c, scenario="after", time_slot="08:00"
        ).first()
        roads.append({
            "name": c.name,
            "code": c.code,
            "from_x": c.zone_from.map_x,
            "from_y": c.zone_from.map_y,
            "to_x": c.zone_to.map_x,
            "to_y": c.zone_to.map_y,
            "congestion_before": before_slice.congestion_level if before_slice else 0.85,
            "congestion_after": after_slice.congestion_level if after_slice else 0.35,
        })

    # Carpool hubs
    hubs = CarpoolHub.objects.all()
    hub_list = [
        {"name": h.name, "x": h.map_x, "y": h.map_y}
        for h in hubs
    ]

    return JsonResponse({
        "landmarks": landmarks,
        "roads": roads,
        "carpool_hubs": hub_list,
        "avg_congestion_before": run.peak_congestion_before or 0.87,
        "avg_congestion_after": run.peak_congestion_after or 0.38,
    })


def api_corridors(request, run_id):
    """Return time-sliced corridor data for chart rendering."""
    run = get_object_or_404(SimulationRun, pk=run_id)
    scenario = request.GET.get("scenario", "before")
    logger.info("API corridors requested for run_id=%d scenario=%s", run_id, scenario)

    slices = CorridorTimeSlice.objects.filter(
        simulation_run=run, scenario=scenario
    ).select_related("corridor").order_by("time_slot", "corridor__name")

    data = [
        {
            "corridor": s.corridor.name,
            "corridor_code": s.corridor.code,
            "time_slot": s.time_slot,
            "volume": s.volume,
            "capacity_ratio": round(s.capacity_ratio, 3),
            "travel_time_min": round(s.travel_time_min, 1),
            "speed_kmh": round(s.speed_kmh, 1),
            "congestion_level": round(s.congestion_level, 3),
        }
        for s in slices
    ]
    return JsonResponse({"scenario": scenario, "slices": data})


def api_companies(request, run_id):
    """Return company coordination table data."""
    run = get_object_or_404(SimulationRun, pk=run_id)
    logger.info("API companies requested for run_id=%d", run_id)

    results = CompanySimResult.objects.filter(
        simulation_run=run
    ).select_related("company", "company__office_zone").order_by("-company__total_staff")

    companies = []
    for r in results:
        c = r.company
        load_before = r.staff_on_road_before / max(c.total_staff, 1)
        load_after = r.staff_on_road_after / max(c.total_staff, 1)
        companies.append({
            "code": c.code,
            "name": c.name,
            "sector": c.sector,
            "staff": c.total_staff,
            "zone": c.office_zone.name,
            "default_start": c.default_start_time.strftime("%H:%M"),
            "assigned_start": r.assigned_start_time.strftime("%H:%M") if r.assigned_start_time else c.default_start_time.strftime("%H:%M"),
            "wfh_count": r.wfh_count,
            "carpool_count": r.carpool_count,
            "load_before": round(min(load_before, 1.0), 2),
            "load_after": round(min(load_after, 1.0), 2),
            "load_contribution": round(r.load_contribution, 3),
        })

    return JsonResponse({"companies": companies})


def api_chart(request, run_id):
    """Return hourly volume chart data (before vs after)."""
    run = get_object_or_404(SimulationRun, pk=run_id)
    logger.info("API chart requested for run_id=%d", run_id)

    hours = ["6AM", "7AM", "8AM", "9AM", "10AM", "11AM", "12PM", "1PM", "2PM", "3PM", "4PM", "5PM", "6PM", "7PM"]
    hour_slots = ["06:00", "07:00", "08:00", "09:00", "10:00", "11:00", "12:00", "13:00",
                  "14:00", "15:00", "16:00", "17:00", "18:00", "19:00"]

    before_volumes = []
    after_volumes = []

    for slot in hour_slots:
        before_avg = CorridorTimeSlice.objects.filter(
            simulation_run=run, scenario="before", time_slot=slot
        ).values_list("congestion_level", flat=True)
        after_avg = CorridorTimeSlice.objects.filter(
            simulation_run=run, scenario="after", time_slot=slot
        ).values_list("congestion_level", flat=True)

        b_list = list(before_avg)
        a_list = list(after_avg)
        before_volumes.append(round((sum(b_list) / max(len(b_list), 1)) * 100, 1))
        after_volumes.append(round((sum(a_list) / max(len(a_list), 1)) * 100, 1))

    return JsonResponse({
        "hours": hours,
        "before_volumes": before_volumes,
        "after_volumes": after_volumes,
    })


def api_stagger(request, run_id):
    """Return stagger distribution data."""
    run = get_object_or_404(SimulationRun, pk=run_id)
    logger.info("API stagger requested for run_id=%d", run_id)

    results = CompanySimResult.objects.filter(simulation_run=run).select_related("company")
    time_labels = ["07:00", "07:30", "08:00", "08:30", "09:00", "09:30", "10:00", "10:30"]
    slot_labels = ["7:00 AM", "7:30 AM", "8:00 AM", "8:30 AM", "9:00 AM", "9:30 AM", "10:00AM", "10:30AM"]
    slot_names = ["Early Bird", "Early", "Standard", "Standard+", "Mid-shift", "Mid+", "Flex", "Extended"]

    # Count staff per stagger slot (in thousands)
    before_counts = {}
    after_counts = {}
    for t in time_labels:
        before_counts[t] = 0
        after_counts[t] = 0

    for r in results:
        c = r.company
        default_str = c.default_start_time.strftime("%H:%M")
        assigned_str = r.assigned_start_time.strftime("%H:%M") if r.assigned_start_time else default_str

        # Round to nearest slot
        before_slot = _nearest_slot(default_str, time_labels)
        after_slot = _nearest_slot(assigned_str, time_labels)
        staff_k = round(c.total_staff / 1000, 1)
        before_counts[before_slot] = before_counts.get(before_slot, 0) + staff_k
        after_counts[after_slot] = after_counts.get(after_slot, 0) + staff_k

    slots = []
    for i, t in enumerate(time_labels):
        slots.append({
            "time": slot_labels[i],
            "label": slot_names[i],
            "count_before": round(before_counts.get(t, 0)),
            "count_after": round(after_counts.get(t, 0)),
        })

    return JsonResponse({"slots": slots})


def _nearest_slot(time_str, slots):
    """Find the nearest slot label for a given time string."""
    try:
        h, m = map(int, time_str.split(":"))
        target = h * 60 + m
    except (ValueError, AttributeError):
        return slots[2]  # Default to 08:00

    best = slots[0]
    best_diff = 9999
    for s in slots:
        sh, sm = map(int, s.split(":"))
        diff = abs((sh * 60 + sm) - target)
        if diff < best_diff:
            best_diff = diff
            best = s
    return best


def api_carpools(request, run_id):
    """Return carpool group list."""
    run = get_object_or_404(SimulationRun, pk=run_id)
    logger.info("API carpools requested for run_id=%d", run_id)

    groups = CarpoolGroup.objects.filter(
        simulation_run=run
    ).select_related("hub", "hub__zone").prefetch_related("memberships")[:20]

    group_list = [
        {
            "name": g.name,
            "route": g.route_description,
            "departure": g.departure_time.strftime("%H:%M"),
            "max_seats": g.max_seats,
            "members": g.current_members,
            "hub": g.hub.name if g.hub else "Direct",
        }
        for g in groups
    ]

    return JsonResponse({"groups": group_list, "total": run.total_carpool_groups or 0})


def api_wfh(request, run_id):
    """Return WFH calendar data for top companies."""
    run = get_object_or_404(SimulationRun, pk=run_id)
    logger.info("API wfh requested for run_id=%d", run_id)

    from company.models import StaffSchedule
    results = CompanySimResult.objects.filter(
        simulation_run=run
    ).select_related("company").order_by("-company__total_staff")[:8]

    companies = []
    for r in results:
        c = r.company
        # Determine WFH days for this company
        schedules = StaffSchedule.objects.filter(
            simulation_run=run,
            staff__company=c,
        ).values_list("day_of_week", "location")

        # Aggregate: for each day, is it mostly WFH or office?
        day_counts = {d: {"OFF": 0, "WFH": 0} for d in range(5)}
        for day, loc in schedules:
            if day < 5:
                day_counts[day][loc] = day_counts[day].get(loc, 0) + 1

        days = []
        for d in range(5):
            if day_counts[d]["WFH"] > day_counts[d]["OFF"]:
                days.append("H")
            else:
                days.append("O")

        companies.append({
            "code": c.code,
            "name": c.name,
            "days": days,
            "wfh_count": r.wfh_count,
        })

    return JsonResponse({
        "companies": companies,
        "wfh_today": run.total_wfh_today or 0,
    })


def api_transit(request, run_id):
    """Return transit line load data."""
    run = get_object_or_404(SimulationRun, pk=run_id)
    logger.info("API transit requested for run_id=%d", run_id)

    lines = TransitLine.objects.all()
    total_cap = sum(l.capacity_per_hour for l in lines)

    # Estimate load based on modal split and run parameters
    pub_split = ModalSplit.objects.filter(mode="PUB").first()
    pub_pct = pub_split.share_pct if pub_split else 12.0

    transit_data = []
    for l in lines:
        cap_share = l.capacity_per_hour / max(total_cap, 1)
        # Before: higher load due to concentrated peak
        before_load_pct = min(95, int(50 + cap_share * 200 + pub_pct))
        # After: lower due to stagger + WFH reducing peak demand
        after_load_pct = max(25, before_load_pct - 20)

        transit_data.append({
            "code": l.code,
            "name": l.name,
            "mode": l.mode,
            "route": l.route_description,
            "color": l.color,
            "capacity": l.capacity_per_hour,
            "pct_before": str(before_load_pct) + "%",
            "pct_after": str(after_load_pct) + "%",
            "load_before": "high" if before_load_pct > 75 else ("med" if before_load_pct > 50 else "low"),
            "load_after": "high" if after_load_pct > 75 else ("med" if after_load_pct > 50 else "low"),
        })

    return JsonResponse({"lines": transit_data})
