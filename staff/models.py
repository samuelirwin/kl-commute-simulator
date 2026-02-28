"""
Staff app models — carpool groups and memberships formed by the matching algorithm.
"""
from django.db import models

from company.models import StaffMember
from core.models import CarpoolHub


class CarpoolGroup(models.Model):
    """A matched carpool group with a driver and passengers sharing a route."""

    name = models.CharField(max_length=100)
    hub = models.ForeignKey(CarpoolHub, on_delete=models.SET_NULL, null=True, blank=True, related_name="groups")
    route_description = models.CharField(max_length=200, blank=True)
    departure_time = models.TimeField()
    max_seats = models.PositiveIntegerField(default=4)
    simulation_run = models.ForeignKey(
        "simulation.SimulationRun", on_delete=models.CASCADE, related_name="carpool_groups"
    )

    def __str__(self):
        return f"{self.name} — {self.route_description}"

    @property
    def current_members(self):
        return self.memberships.count()


class CarpoolMembership(models.Model):
    """Links a staff member to a carpool group as driver or passenger."""

    ROLE_CHOICES = [
        ("DRV", "Driver"),
        ("PSG", "Passenger"),
    ]

    staff = models.ForeignKey(StaffMember, on_delete=models.CASCADE, related_name="carpool_memberships")
    group = models.ForeignKey(CarpoolGroup, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=3, choices=ROLE_CHOICES)

    class Meta:
        unique_together = ("staff", "group")

    def __str__(self):
        return f"{self.staff.name} — {self.get_role_display()} in {self.group.name}"
