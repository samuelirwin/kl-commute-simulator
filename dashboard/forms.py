"""
Simulation parameter form — backend validation for running new simulations.
"""
from datetime import time

from django import forms


class SimulationParameterForm(forms.Form):
    """Form for configuring and running a new simulation."""

    name = forms.CharField(
        max_length=200,
        initial="Dashboard Simulation",
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Run name"}),
    )
    enable_stagger = forms.BooleanField(required=False, initial=True)
    enable_wfh = forms.BooleanField(required=False, initial=True)
    enable_carpool = forms.BooleanField(required=False, initial=True)
    enable_transit_boost = forms.BooleanField(required=False, initial=True)

    stagger_window_start = forms.TimeField(
        required=False, initial=time(7, 0),
        widget=forms.TimeInput(attrs={"type": "time"}),
    )
    stagger_window_end = forms.TimeField(
        required=False, initial=time(10, 30),
        widget=forms.TimeInput(attrs={"type": "time"}),
    )
    wfh_max_days = forms.IntegerField(
        min_value=0, max_value=5, initial=2,
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )
    wfh_sector_cap_pct = forms.IntegerField(
        min_value=10, max_value=80, initial=40,
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )
    carpool_max_detour_km = forms.FloatField(
        min_value=1.0, max_value=20.0, initial=5.0,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.5"}),
    )
    transit_frequency_boost_pct = forms.IntegerField(
        min_value=0, max_value=50, initial=20,
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get("stagger_window_start")
        end = cleaned.get("stagger_window_end")
        if start and end and start >= end:
            raise forms.ValidationError("Stagger window start must be before end.")
        return cleaned
