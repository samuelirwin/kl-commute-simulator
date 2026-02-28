"""Public staff app URL routes — personal commute dashboard."""
from django.urls import path

from staff import views

app_name = "staff"

urlpatterns = [
    path("", views.index, name="index"),
    path("schedule/", views.my_schedule, name="schedule"),
    path("carpool/", views.my_carpool, name="carpool"),
    path("impact/", views.my_impact, name="impact"),
]
