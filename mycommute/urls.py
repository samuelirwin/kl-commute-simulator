"""
Root URL configuration — routes to dashboard, company, staff portals, and simulation API.
"""
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("dashboard.urls")),
    path("company/", include("company.urls")),
    path("staff/", include("staff.urls")),
    path("api/v1/simulation/", include("simulation.urls")),
]
