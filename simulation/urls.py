"""Simulation API URL routes — JSON endpoints for dashboard data."""
from django.urls import path

from simulation import views

app_name = "simulation"

urlpatterns = [
    path("<int:run_id>/kpis/", views.api_kpis, name="kpis"),
    path("<int:run_id>/map/", views.api_map, name="map"),
    path("<int:run_id>/corridors/", views.api_corridors, name="corridors"),
    path("<int:run_id>/companies/", views.api_companies, name="companies"),
    path("<int:run_id>/chart/", views.api_chart, name="chart"),
    path("<int:run_id>/stagger/", views.api_stagger, name="stagger"),
    path("<int:run_id>/carpools/", views.api_carpools, name="carpools"),
    path("<int:run_id>/wfh/", views.api_wfh, name="wfh"),
    path("<int:run_id>/transit/", views.api_transit, name="transit"),
]
