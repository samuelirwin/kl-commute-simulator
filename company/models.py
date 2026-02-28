"""
Company models — organizations, departments, and staff members participating in the commute
coordination system. Each company has a zone-based office location and configurable WFH policy.
"""
from django.db import models

from core.models import Zone


class Company(models.Model):
    """Organization registered in the MyCommute system."""

    SECTOR_CHOICES = [
        ("Energy", "Energy"),
        ("Banking", "Banking"),
        ("Telecom", "Telecom"),
        ("Aviation", "Aviation"),
        ("Conglomerate", "Conglomerate"),
        ("Media", "Media"),
        ("Government", "Government"),
        ("Technology", "Technology"),
        ("Construction", "Construction"),
        ("Manufacturing", "Manufacturing"),
    ]

    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20, unique=True)
    sector = models.CharField(max_length=20, choices=SECTOR_CHOICES)
    total_staff = models.PositiveIntegerField()
    office_zone = models.ForeignKey(Zone, on_delete=models.CASCADE, related_name="companies")
    default_start_time = models.TimeField()
    is_glc = models.BooleanField(default=False, help_text="Government-linked company")
    wfh_days_per_week = models.PositiveIntegerField(default=1)
    compliance_score = models.FloatField(default=0.0, help_text="0-100 compliance rating")

    class Meta:
        verbose_name_plural = "companies"
        ordering = ["-total_staff"]

    def __str__(self):
        return f"{self.name} ({self.code})"


class Department(models.Model):
    """Department within a company, with WFH eligibility flag."""

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="departments")
    name = models.CharField(max_length=100)
    staff_count = models.PositiveIntegerField(default=0)
    can_wfh = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.company.code} — {self.name}"


class StaffMember(models.Model):
    """Individual staff member with commute preferences and transport details."""

    TRANSPORT_CHOICES = [
        ("CAR", "Private Car"),
        ("MCY", "Motorcycle"),
        ("PUB", "Public Transit"),
        ("EHL", "E-Hailing"),
        ("CPL", "Carpool"),
    ]

    employee_id = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=100)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="staff_members")
    department = models.ForeignKey(Department, on_delete=models.CASCADE, related_name="staff_members")
    home_zone = models.ForeignKey(Zone, on_delete=models.CASCADE, related_name="residents")
    primary_transport = models.CharField(max_length=3, choices=TRANSPORT_CHOICES, default="CAR")
    has_vehicle = models.BooleanField(default=True)
    willing_to_carpool = models.BooleanField(default=False)
    carpool_seats = models.PositiveIntegerField(default=0, help_text="Seats offered if driver")
    can_wfh = models.BooleanField(default=True)

    class Meta:
        ordering = ["company", "name"]

    def __str__(self):
        return f"{self.name} ({self.employee_id})"


class StaffSchedule(models.Model):
    """Assigned weekly schedule for a staff member within a simulation run."""

    LOCATION_CHOICES = [
        ("OFF", "Office"),
        ("WFH", "Work From Home"),
    ]

    staff = models.ForeignKey(StaffMember, on_delete=models.CASCADE, related_name="schedules")
    simulation_run = models.ForeignKey(
        "simulation.SimulationRun", on_delete=models.CASCADE, related_name="staff_schedules"
    )
    day_of_week = models.PositiveIntegerField(help_text="0=Monday, 4=Friday")
    location = models.CharField(max_length=3, choices=LOCATION_CHOICES, default="OFF")
    assigned_start_time = models.TimeField(null=True, blank=True)
    departure_window = models.CharField(max_length=20, blank=True, help_text="e.g. 07:15 - 07:45")
    estimated_commute_min = models.FloatField(default=0.0)

    class Meta:
        unique_together = ("staff", "simulation_run", "day_of_week")
        ordering = ["staff", "day_of_week"]

    def __str__(self):
        day_names = ["Mon", "Tue", "Wed", "Thu", "Fri"]
        day = day_names[self.day_of_week] if self.day_of_week < 5 else "?"
        return f"{self.staff.name} — {day} — {self.location}"
