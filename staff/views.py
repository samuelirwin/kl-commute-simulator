"""
Public staff app views — personal commute dashboard, schedule, carpool info, impact stats.
Staff is selected via ?staff_id=N URL parameter (no auth for simulation purposes).
"""
import logging

from django.http import Http404
from django.shortcuts import get_object_or_404, render

from company.models import StaffMember, StaffSchedule
from simulation.models import CompanySimResult, SimulationRun
from staff.models import CarpoolGroup, CarpoolMembership

logger = logging.getLogger("staff")


def _get_staff(request):
    """Get staff member from URL param, default to first staff."""
    staff_id = request.GET.get("staff_id", "")
    if staff_id:
        return get_object_or_404(StaffMember, pk=staff_id)
    return StaffMember.objects.first()


def index(request):
    """Personal dashboard home with commute overview."""
    staff = _get_staff(request)
    if not staff:
        return render(request, "staff/index.html", {"nav_active": "staff", "staff_member": None})

    latest_run = SimulationRun.objects.filter(status="CMP").first()
    schedules = []
    if latest_run:
        schedules = StaffSchedule.objects.filter(
            staff=staff, simulation_run=latest_run
        ).order_by("day_of_week")

    # Get carpool membership
    carpool_membership = CarpoolMembership.objects.filter(
        staff=staff
    ).select_related("group", "group__hub").first()

    logger.info("Staff portal loaded for %s (id=%d)", staff.name, staff.pk)
    return render(request, "staff/index.html", {
        "nav_active": "staff",
        "staff_member": staff,
        "staff_id": staff.pk,
        "schedules": schedules,
        "carpool_membership": carpool_membership,
        "latest_run": latest_run,
    })


def my_schedule(request):
    """Weekly schedule view for this staff member."""
    staff = _get_staff(request)
    if not staff:
        raise Http404("No staff found")

    latest_run = SimulationRun.objects.filter(status="CMP").first()
    schedules = []
    if latest_run:
        schedules = StaffSchedule.objects.filter(
            staff=staff, simulation_run=latest_run
        ).order_by("day_of_week")

    logger.info("Schedule view for staff %s", staff.name)
    return render(request, "staff/schedule.html", {
        "nav_active": "staff",
        "staff_member": staff,
        "staff_id": staff.pk,
        "schedules": schedules,
    })


def my_carpool(request):
    """Carpool group details for this staff member."""
    staff = _get_staff(request)
    if not staff:
        raise Http404("No staff found")

    membership = CarpoolMembership.objects.filter(
        staff=staff
    ).select_related("group", "group__hub").first()

    group_members = []
    if membership:
        group_members = CarpoolMembership.objects.filter(
            group=membership.group
        ).select_related("staff", "staff__home_zone")

    logger.info("Carpool view for staff %s", staff.name)
    return render(request, "staff/carpool.html", {
        "nav_active": "staff",
        "staff_member": staff,
        "staff_id": staff.pk,
        "membership": membership,
        "group_members": group_members,
    })


def my_impact(request):
    """Personal impact stats — how much this staff member's coordination saves."""
    staff = _get_staff(request)
    if not staff:
        raise Http404("No staff found")

    latest_run = SimulationRun.objects.filter(status="CMP").first()
    schedules = []
    company_result = None
    if latest_run:
        schedules = StaffSchedule.objects.filter(
            staff=staff, simulation_run=latest_run
        ).order_by("day_of_week")
        company_result = CompanySimResult.objects.filter(
            simulation_run=latest_run, company=staff.company
        ).first()

    # Calculate personal stats
    wfh_days = sum(1 for s in schedules if s.location == "WFH")
    office_days = sum(1 for s in schedules if s.location == "OFF")
    avg_commute = 0
    if office_days > 0:
        commute_times = [s.estimated_commute_min for s in schedules if s.location == "OFF" and s.estimated_commute_min > 0]
        avg_commute = round(sum(commute_times) / max(len(commute_times), 1), 1)

    # Rough CO2 savings estimate per person
    # Avg 15km commute, 171g/km car, 2 trips/day, WFH days saved
    co2_saved_kg = round(wfh_days * 15 * 0.171 * 2, 1)

    logger.info("Impact view for staff %s: wfh=%d, co2_saved=%.1fkg", staff.name, wfh_days, co2_saved_kg)
    return render(request, "staff/impact.html", {
        "nav_active": "staff",
        "staff_member": staff,
        "staff_id": staff.pk,
        "wfh_days": wfh_days,
        "office_days": office_days,
        "avg_commute": avg_commute,
        "co2_saved_kg": co2_saved_kg,
        "company_result": company_result,
        "latest_run": latest_run,
    })
