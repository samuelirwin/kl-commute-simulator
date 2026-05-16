"""
Simulation models — stores run configurations, time-sliced corridor results,
and per-company outcome data.
"""
from django.db import models

from company.models import Company
from core.models import Corridor


class SimulationRun(models.Model):
    """A single simulation execution with parameters and aggregated results."""

    STATUS_CHOICES = [
        ("PND", "Pending"),
        ("RUN", "Running"),
        ("CMP", "Completed"),
        ("ERR", "Error"),
    ]

    name = models.CharField(max_length=200, default="Untitled Run")
    status = models.CharField(max_length=3, choices=STATUS_CHOICES, default="PND")
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    # Toggle flags for which measures are enabled
    enable_stagger = models.BooleanField(default=True)
    enable_wfh = models.BooleanField(default=True)
    enable_carpool = models.BooleanField(default=True)
    enable_transit_boost = models.BooleanField(default=True)

    # Parameters
    stagger_window_start = models.TimeField(null=True, blank=True)
    stagger_window_end = models.TimeField(null=True, blank=True)
    wfh_max_days = models.PositiveIntegerField(default=2)
    wfh_sector_cap_pct = models.PositiveIntegerField(default=40, help_text="Max % of any sector WFH same day")
    carpool_max_detour_km = models.FloatField(default=5.0)
    transit_frequency_boost_pct = models.PositiveIntegerField(default=20)
    workforce_multiplier = models.FloatField(
        default=1.0,
        help_text="Scale factor applied to company total_staff for simulation",
    )
    carpool_willingness_pct = models.PositiveIntegerField(
        default=35,
        help_text="Percentage of staff willing to carpool as driver or rider",
    )
    wfh_eligibility_pct = models.PositiveIntegerField(
        default=80,
        help_text="Percentage of staff eligible for WFH",
    )
    car_mode_share_pct = models.FloatField(
        default=67.0,
        help_text="Percentage of commuters using private car",
    )
    motorcycle_mode_share_pct = models.FloatField(
        default=17.0,
        help_text="Percentage of commuters using motorcycle",
    )
    public_transit_share_pct = models.FloatField(
        default=12.0,
        help_text="Percentage of commuters using public transit",
    )

    # Aggregated results (populated after simulation completes)
    peak_congestion_before = models.FloatField(null=True, blank=True)
    peak_congestion_after = models.FloatField(null=True, blank=True)
    avg_commute_before = models.FloatField(null=True, blank=True, help_text="Minutes")
    avg_commute_after = models.FloatField(null=True, blank=True, help_text="Minutes")
    peak_vehicles_before = models.PositiveIntegerField(null=True, blank=True)
    peak_vehicles_after = models.PositiveIntegerField(null=True, blank=True)
    co2_saved_tonnes = models.FloatField(null=True, blank=True)
    total_carpool_groups = models.PositiveIntegerField(null=True, blank=True)
    total_wfh_today = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} ({self.get_status_display()})"

    @property
    def congestion_reduction_pct(self):
        if self.peak_congestion_before and self.peak_congestion_after:
            return round(
                (1 - self.peak_congestion_after / self.peak_congestion_before) * 100, 1
            )
        return 0

    @property
    def commute_reduction_pct(self):
        if self.avg_commute_before and self.avg_commute_after:
            return round(
                (1 - self.avg_commute_after / self.avg_commute_before) * 100, 1
            )
        return 0

    @property
    def vehicles_removed(self):
        if self.peak_vehicles_before and self.peak_vehicles_after:
            return self.peak_vehicles_before - self.peak_vehicles_after
        return 0


class CorridorTimeSlice(models.Model):
    """Traffic data for a specific corridor at a 15-minute time slot."""

    SCENARIO_CHOICES = [
        ("before", "Before (Status Quo)"),
        ("after", "After (MyCommute Active)"),
    ]

    simulation_run = models.ForeignKey(
        SimulationRun, on_delete=models.CASCADE, related_name="corridor_slices"
    )
    corridor = models.ForeignKey(Corridor, on_delete=models.CASCADE, related_name="time_slices")
    time_slot = models.CharField(max_length=5, help_text="HH:MM format, e.g. 07:30")
    scenario = models.CharField(max_length=6, choices=SCENARIO_CHOICES)

    volume = models.PositiveIntegerField(default=0, help_text="Total PCE volume")
    volume_car = models.PositiveIntegerField(default=0)
    volume_motorcycle = models.PositiveIntegerField(default=0)
    capacity_ratio = models.FloatField(default=0.0, help_text="V/C ratio")
    travel_time_min = models.FloatField(default=0.0)
    speed_kmh = models.FloatField(default=0.0)
    congestion_level = models.FloatField(default=0.0, help_text="0-1 congestion index")

    class Meta:
        ordering = ["simulation_run", "corridor", "time_slot", "scenario"]
        indexes = [
            models.Index(fields=["simulation_run", "scenario", "time_slot"]),
        ]

    def __str__(self):
        return f"{self.corridor.code} @ {self.time_slot} ({self.scenario})"


class CompanySimResult(models.Model):
    """Per-company results within a simulation run."""

    simulation_run = models.ForeignKey(
        SimulationRun, on_delete=models.CASCADE, related_name="company_results"
    )
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="sim_results")
    assigned_start_time = models.TimeField(null=True, blank=True)
    staff_on_road_before = models.PositiveIntegerField(default=0)
    staff_on_road_after = models.PositiveIntegerField(default=0)
    wfh_count = models.PositiveIntegerField(default=0)
    carpool_count = models.PositiveIntegerField(default=0)
    load_contribution = models.FloatField(default=0.0, help_text="0-1 fraction of peak load")

    class Meta:
        unique_together = ("simulation_run", "company")
        ordering = ["simulation_run", "-load_contribution"]

    def __str__(self):
        return f"{self.company.code} — Run #{self.simulation_run_id}"
