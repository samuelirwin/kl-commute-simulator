"""Dashboard URL routes — government-level simulation dashboard."""
from django.urls import path

from dashboard import views

app_name = "dashboard"

urlpatterns = [
    path("", views.index, name="index"),
    path("dashboard/simulate/", views.run_simulation, name="simulate"),
    path("dashboard/run/<int:run_id>/", views.run_detail, name="run_detail"),
]
