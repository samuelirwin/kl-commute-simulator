"""Django admin configuration for staff models."""
from django.contrib import admin

from staff.models import CarpoolGroup, CarpoolMembership


@admin.register(CarpoolGroup)
class CarpoolGroupAdmin(admin.ModelAdmin):
    list_display = ("name", "hub", "departure_time", "max_seats", "simulation_run")
    list_filter = ("simulation_run",)
    search_fields = ("name", "route_description")


@admin.register(CarpoolMembership)
class CarpoolMembershipAdmin(admin.ModelAdmin):
    list_display = ("staff", "group", "role")
    list_filter = ("role",)
    raw_id_fields = ("staff", "group")
