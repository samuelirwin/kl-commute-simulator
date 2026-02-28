"""Django admin configuration for company models."""
from django.contrib import admin

from company.models import Company, Department, StaffMember, StaffSchedule


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "sector", "total_staff", "office_zone", "is_glc", "wfh_days_per_week")
    list_filter = ("sector", "is_glc")
    search_fields = ("name", "code")


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ("name", "company", "staff_count", "can_wfh")
    list_filter = ("can_wfh", "company")


@admin.register(StaffMember)
class StaffMemberAdmin(admin.ModelAdmin):
    list_display = ("employee_id", "name", "company", "department", "home_zone", "primary_transport", "can_wfh")
    list_filter = ("company", "primary_transport", "can_wfh", "willing_to_carpool")
    search_fields = ("name", "employee_id")


@admin.register(StaffSchedule)
class StaffScheduleAdmin(admin.ModelAdmin):
    list_display = ("staff", "simulation_run", "day_of_week", "location", "assigned_start_time")
    list_filter = ("location", "day_of_week")
    raw_id_fields = ("staff", "simulation_run")
