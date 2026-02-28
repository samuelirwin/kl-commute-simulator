"""Company admin portal URL routes."""
from django.urls import path

from company import views

app_name = "company"

urlpatterns = [
    path("", views.index, name="index"),
    path("staff/", views.staff_list, name="staff_list"),
    path("staff/add/", views.staff_add, name="staff_add"),
    path("staff/<int:staff_id>/edit/", views.staff_edit, name="staff_edit"),
    path("schedule/", views.schedule_view, name="schedule"),
    path("compliance/", views.compliance, name="compliance"),
]
