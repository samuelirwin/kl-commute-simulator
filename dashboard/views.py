"""
Dashboard views — government-level simulation dashboard with form to run new simulations.
"""
import logging

from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from dashboard.forms import SimulationParameterForm
from simulation.models import SimulationRun

logger = logging.getLogger("mycommute")


def index(request):
    """Main dashboard page — loads the latest completed simulation run."""
    latest_run = SimulationRun.objects.filter(status="CMP").first()
    runs = SimulationRun.objects.all()[:10]
    form = SimulationParameterForm()

    logger.info("Dashboard index loaded, latest_run=%s", latest_run)
    return render(request, "dashboard/index.html", {
        "nav_active": "dashboard",
        "run": latest_run,
        "runs": runs,
        "form": form,
    })


def run_simulation(request):
    """POST: Create and execute a new simulation run."""
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    form = SimulationParameterForm(request.POST)
    if not form.is_valid():
        logger.warning("Simulation form invalid: %s", form.errors)
        return JsonResponse({"errors": form.errors}, status=400)

    run = SimulationRun.objects.create(
        name=form.cleaned_data.get("name", "Dashboard Run"),
        enable_stagger=form.cleaned_data.get("enable_stagger", True),
        enable_wfh=form.cleaned_data.get("enable_wfh", True),
        enable_carpool=form.cleaned_data.get("enable_carpool", True),
        enable_transit_boost=form.cleaned_data.get("enable_transit_boost", True),
        stagger_window_start=form.cleaned_data.get("stagger_window_start"),
        stagger_window_end=form.cleaned_data.get("stagger_window_end"),
        wfh_max_days=form.cleaned_data.get("wfh_max_days", 2),
        wfh_sector_cap_pct=form.cleaned_data.get("wfh_sector_cap_pct", 40),
        carpool_max_detour_km=form.cleaned_data.get("carpool_max_detour_km", 5.0),
        transit_frequency_boost_pct=form.cleaned_data.get("transit_frequency_boost_pct", 20),
        workforce_multiplier=form.cleaned_data.get("workforce_multiplier", 1.0),
        car_mode_share_pct=form.cleaned_data.get("car_mode_share_pct", 67.0),
        motorcycle_mode_share_pct=form.cleaned_data.get("motorcycle_mode_share_pct", 17.0),
        public_transit_share_pct=form.cleaned_data.get("public_transit_share_pct", 12.0),
        carpool_willingness_pct=form.cleaned_data.get("carpool_willingness_pct", 35),
        wfh_eligibility_pct=form.cleaned_data.get("wfh_eligibility_pct", 80),
    )
    logger.info("Created simulation run id=%d name='%s'", run.id, run.name)

    # Execute simulation
    try:
        from simulation.engine.runner import execute_simulation
        execute_simulation(run.id)
        logger.info("Simulation run id=%d completed successfully", run.id)
    except Exception as e:
        logger.error("Simulation run id=%d failed: %s", run.id, str(e))
        run.status = "ERR"
        run.save()
        return JsonResponse({"error": str(e)}, status=500)

    return JsonResponse({"run_id": run.id, "redirect": f"/dashboard/run/{run.id}/"})


def run_detail(request, run_id):
    """View results of a specific simulation run."""
    run = get_object_or_404(SimulationRun, pk=run_id)
    logger.info("Dashboard run detail for run_id=%d", run_id)
    return render(request, "dashboard/index.html", {
        "nav_active": "dashboard",
        "run": run,
        "runs": SimulationRun.objects.all()[:10],
        "form": SimulationParameterForm(),
    })
