"""
Company admin portal views — staff CRUD, schedule, and compliance management.
Company is selected via ?company=CODE URL parameter (no auth required for simulation).
"""
import logging

from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render

from company.forms import StaffMemberForm
from company.models import Company, Department, StaffMember, StaffSchedule
from simulation.models import CompanySimResult, SimulationRun

logger = logging.getLogger("company")


def _get_company(request):
    """Extract company from URL param, default to first company."""
    code = request.GET.get("company", "")
    if code:
        return get_object_or_404(Company, code=code)
    return Company.objects.first()


def index(request):
    """Company admin home — overview stats."""
    company = _get_company(request)
    if not company:
        return render(request, "company/index.html", {"nav_active": "company", "company": None})

    companies = Company.objects.all()
    latest_run = SimulationRun.objects.filter(status="CMP").first()
    sim_result = None
    if latest_run:
        sim_result = CompanySimResult.objects.filter(
            simulation_run=latest_run, company=company
        ).first()

    staff_count = StaffMember.objects.filter(company=company).count()
    departments = Department.objects.filter(company=company)

    logger.info("Company index loaded for %s (staff=%d)", company.code, staff_count)
    return render(request, "company/index.html", {
        "nav_active": "company",
        "company": company,
        "company_code": company.code,
        "companies": companies,
        "staff_count": staff_count,
        "departments": departments,
        "sim_result": sim_result,
        "latest_run": latest_run,
    })


def staff_list(request):
    """List all staff for the selected company."""
    company = _get_company(request)
    if not company:
        raise Http404("No company found")

    staff = StaffMember.objects.filter(
        company=company
    ).select_related("department", "home_zone").order_by("name")

    logger.info("Staff list for %s (%d staff)", company.code, staff.count())
    return render(request, "company/staff_list.html", {
        "nav_active": "company",
        "company": company,
        "company_code": company.code,
        "staff": staff,
    })


def staff_add(request):
    """Add a new staff member with validated form."""
    company = _get_company(request)
    if not company:
        raise Http404("No company found")

    if request.method == "POST":
        form = StaffMemberForm(request.POST, company=company)
        if form.is_valid():
            staff = form.save()
            logger.info("Staff added: %s (%s) to %s", staff.name, staff.employee_id, company.code)
            return redirect(f"/company/staff/?company={company.code}")
        else:
            logger.warning("Staff add form invalid: %s", form.errors)
    else:
        form = StaffMemberForm(company=company)

    return render(request, "company/staff_form.html", {
        "nav_active": "company",
        "company": company,
        "company_code": company.code,
        "form": form,
        "action": "Add",
    })


def staff_edit(request, staff_id):
    """Edit an existing staff member."""
    staff = get_object_or_404(StaffMember, pk=staff_id)
    company = staff.company

    if request.method == "POST":
        form = StaffMemberForm(request.POST, instance=staff, company=company)
        if form.is_valid():
            form.save()
            logger.info("Staff updated: %s (%s)", staff.name, staff.employee_id)
            return redirect(f"/company/staff/?company={company.code}")
        else:
            logger.warning("Staff edit form invalid: %s", form.errors)
    else:
        form = StaffMemberForm(instance=staff, company=company)

    return render(request, "company/staff_form.html", {
        "nav_active": "company",
        "company": company,
        "company_code": company.code,
        "form": form,
        "action": "Edit",
        "staff": staff,
    })


def schedule_view(request):
    """Weekly schedule view for all staff in the company."""
    company = _get_company(request)
    if not company:
        raise Http404("No company found")

    latest_run = SimulationRun.objects.filter(status="CMP").first()
    schedules = []
    if latest_run:
        schedules = StaffSchedule.objects.filter(
            simulation_run=latest_run,
            staff__company=company,
        ).select_related("staff").order_by("staff__name", "day_of_week")

    # Group by staff
    staff_schedules = {}
    for s in schedules:
        if s.staff_id not in staff_schedules:
            staff_schedules[s.staff_id] = {
                "name": s.staff.name,
                "employee_id": s.staff.employee_id,
                "days": [None] * 5,
            }
        if s.day_of_week < 5:
            staff_schedules[s.staff_id]["days"][s.day_of_week] = s

    logger.info("Schedule view for %s (%d staff)", company.code, len(staff_schedules))
    return render(request, "company/schedule_view.html", {
        "nav_active": "company",
        "company": company,
        "company_code": company.code,
        "staff_schedules": list(staff_schedules.values()),
    })


def compliance(request):
    """Compliance dashboard showing company adherence to coordination measures."""
    company = _get_company(request)
    if not company:
        raise Http404("No company found")

    companies = Company.objects.all().order_by("-compliance_score")
    latest_run = SimulationRun.objects.filter(status="CMP").first()
    results = []
    if latest_run:
        results = CompanySimResult.objects.filter(
            simulation_run=latest_run
        ).select_related("company").order_by("-company__compliance_score")

    logger.info("Compliance view loaded")
    return render(request, "company/compliance.html", {
        "nav_active": "company",
        "company": company,
        "company_code": company.code,
        "companies": companies,
        "results": results,
    })
