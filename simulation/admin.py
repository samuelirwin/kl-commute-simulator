"""Django admin configuration for simulation models."""
from django.contrib import admin

from simulation.models import CompanySimResult, CorridorTimeSlice, SimulationRun


@admin.register(SimulationRun)
class SimulationRunAdmin(admin.ModelAdmin):
    list_display = ("name", "status", "created_at", "peak_congestion_before", "peak_congestion_after", "co2_saved_tonnes")
    list_filter = ("status",)
    search_fields = ("name",)


@admin.register(CorridorTimeSlice)
class CorridorTimeSliceAdmin(admin.ModelAdmin):
    list_display = ("corridor", "time_slot", "scenario", "volume", "congestion_level", "travel_time_min")
    list_filter = ("scenario", "simulation_run")
    raw_id_fields = ("simulation_run", "corridor")


@admin.register(CompanySimResult)
class CompanySimResultAdmin(admin.ModelAdmin):
    list_display = ("company", "simulation_run", "assigned_start_time", "staff_on_road_before", "staff_on_road_after", "wfh_count")
    list_filter = ("simulation_run",)
    raw_id_fields = ("simulation_run", "company")
