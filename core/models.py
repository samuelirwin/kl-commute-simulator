"""
Core models — shared reference data for zones, corridors, transit, carpool hubs, and modal split.
These represent the physical infrastructure and transport characteristics of Klang Valley.
"""
from django.db import models

from core.validators import validate_coordinate, validate_positive


class Zone(models.Model):
    """Geographic zone within Klang Valley (e.g. KLCC, Subang Jaya, Shah Alam)."""

    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20, unique=True)
    latitude = models.FloatField(default=0.0)
    longitude = models.FloatField(default=0.0)
    map_x = models.FloatField(validators=[validate_coordinate], help_text="Canvas X coord 0-1")
    map_y = models.FloatField(validators=[validate_coordinate], help_text="Canvas Y coord 0-1")
    is_major = models.BooleanField(default=False)
    icon = models.CharField(max_length=20, default="house")
    population = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.code})"


class Corridor(models.Model):
    """Road segment connecting two zones with traffic capacity and BPR parameters."""

    name = models.CharField(max_length=100)
    code = models.CharField(max_length=30, unique=True)
    zone_from = models.ForeignKey(Zone, on_delete=models.CASCADE, related_name="corridors_from")
    zone_to = models.ForeignKey(Zone, on_delete=models.CASCADE, related_name="corridors_to")
    distance_km = models.FloatField(validators=[validate_positive])
    free_flow_speed_kmh = models.FloatField(validators=[validate_positive])
    capacity_vph = models.PositiveIntegerField(help_text="Vehicles per hour capacity")
    bpr_alpha = models.FloatField(default=0.15)
    bpr_beta = models.FloatField(default=4.0)
    is_tolled = models.BooleanField(default=False)
    toll_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    daily_volume = models.PositiveIntegerField(default=0, help_text="Estimated daily vehicle count")

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.zone_from.code} -> {self.zone_to.code})"

    @property
    def free_flow_time_min(self):
        """Free-flow travel time in minutes."""
        return (self.distance_km / self.free_flow_speed_kmh) * 60


class TransitLine(models.Model):
    """Public transit line (LRT, MRT, BRT, KTM, Monorail, Bus)."""

    MODE_CHOICES = [
        ("LRT", "Light Rail Transit"),
        ("MRT", "Mass Rapid Transit"),
        ("BRT", "Bus Rapid Transit"),
        ("KTM", "KTM Komuter"),
        ("MNR", "Monorail"),
        ("BUS", "Bus"),
    ]

    code = models.CharField(max_length=10, unique=True)
    name = models.CharField(max_length=100)
    mode = models.CharField(max_length=3, choices=MODE_CHOICES)
    capacity_per_hour = models.PositiveIntegerField()
    frequency_minutes = models.FloatField(help_text="Peak frequency in minutes")
    zones_served = models.ManyToManyField(Zone, blank=True, related_name="transit_lines")
    color = models.CharField(max_length=7, default="#00d4ff", help_text="Hex color for UI display")
    route_description = models.CharField(max_length=200, blank=True)

    def __str__(self):
        return f"{self.code} - {self.name}"


class CarpoolHub(models.Model):
    """Park & Ride or carpool meeting point."""

    name = models.CharField(max_length=100)
    zone = models.ForeignKey(Zone, on_delete=models.CASCADE, related_name="carpool_hubs")
    map_x = models.FloatField(validators=[validate_coordinate])
    map_y = models.FloatField(validators=[validate_coordinate])
    capacity = models.PositiveIntegerField(help_text="Max vehicles that can park")

    def __str__(self):
        return f"{self.name} ({self.zone.code})"


class ModalSplit(models.Model):
    """Transport mode share percentages for the region."""

    MODE_CHOICES = [
        ("CAR", "Private Car"),
        ("MCY", "Motorcycle"),
        ("PUB", "Public Transit"),
        ("EHL", "E-Hailing"),
    ]

    mode = models.CharField(max_length=3, choices=MODE_CHOICES, unique=True)
    share_pct = models.FloatField(help_text="Percentage share of total trips")
    avg_occupancy = models.FloatField(default=1.0)
    co2_grams_per_km = models.FloatField(help_text="CO2 emission factor")

    def __str__(self):
        return f"{self.get_mode_display()} — {self.share_pct}%"
