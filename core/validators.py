"""
Shared validators for model and form fields.
"""
from django.core.exceptions import ValidationError


def validate_positive(value):
    """Ensure a numeric value is positive."""
    if value <= 0:
        raise ValidationError(f"Value must be positive, got {value}.")


def validate_percentage(value):
    """Ensure value is between 0 and 100."""
    if not (0 <= value <= 100):
        raise ValidationError(f"Percentage must be between 0 and 100, got {value}.")


def validate_coordinate(value):
    """Ensure map coordinate is between 0 and 1."""
    if not (0.0 <= value <= 1.0):
        raise ValidationError(f"Coordinate must be between 0.0 and 1.0, got {value}.")


def validate_time_string(value):
    """Ensure time string is in HH:MM format."""
    import re
    if not re.match(r"^\d{2}:\d{2}$", value):
        raise ValidationError(f"Time must be in HH:MM format, got '{value}'.")
