"""Django admin configuration for core models."""
from django.contrib import admin

from core.models import CarpoolHub, Corridor, ModalSplit, TransitLine, Zone


@admin.register(Zone)
class ZoneAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "is_major", "population", "map_x", "map_y")
    list_filter = ("is_major",)
    search_fields = ("name", "code")


@admin.register(Corridor)
class CorridorAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "zone_from", "zone_to", "distance_km", "capacity_vph", "is_tolled")
    list_filter = ("is_tolled",)
    search_fields = ("name", "code")


@admin.register(TransitLine)
class TransitLineAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "mode", "capacity_per_hour", "frequency_minutes")
    list_filter = ("mode",)


@admin.register(CarpoolHub)
class CarpoolHubAdmin(admin.ModelAdmin):
    list_display = ("name", "zone", "capacity")


@admin.register(ModalSplit)
class ModalSplitAdmin(admin.ModelAdmin):
    list_display = ("mode", "share_pct", "avg_occupancy", "co2_grams_per_km")
