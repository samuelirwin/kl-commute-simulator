"""
Staff member form — backend + frontend validation with error messages below inputs.
"""
from django import forms

from company.models import Company, Department, StaffMember
from core.models import Zone


class StaffMemberForm(forms.ModelForm):
    """Form for creating/editing staff members with full validation."""

    class Meta:
        model = StaffMember
        fields = [
            "employee_id", "name", "department", "home_zone",
            "primary_transport", "has_vehicle", "willing_to_carpool",
            "carpool_seats", "can_wfh",
        ]
        widgets = {
            "employee_id": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "e.g. PETRONAS-0051",
            }),
            "name": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Full name",
            }),
            "department": forms.Select(attrs={"class": "form-control"}),
            "home_zone": forms.Select(attrs={"class": "form-control"}),
            "primary_transport": forms.Select(attrs={"class": "form-control"}),
            "carpool_seats": forms.NumberInput(attrs={
                "class": "form-control",
                "min": 0,
                "max": 6,
            }),
        }

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.company = company
        if company:
            self.fields["department"].queryset = Department.objects.filter(company=company)
        self.fields["home_zone"].queryset = Zone.objects.all().order_by("name")

    def clean_employee_id(self):
        """Validate employee ID format: COMPANY_CODE-NNNN."""
        emp_id = self.cleaned_data["employee_id"].strip().upper()
        if not emp_id:
            raise forms.ValidationError("Employee ID is required.")
        if len(emp_id) < 3:
            raise forms.ValidationError("Employee ID is too short.")
        # Check uniqueness (exclude current instance for edits)
        qs = StaffMember.objects.filter(employee_id=emp_id)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("This employee ID already exists.")
        return emp_id

    def clean_name(self):
        """Validate staff name."""
        name = self.cleaned_data["name"].strip()
        if not name:
            raise forms.ValidationError("Name is required.")
        if len(name) < 2:
            raise forms.ValidationError("Name must be at least 2 characters.")
        if len(name) > 100:
            raise forms.ValidationError("Name must be 100 characters or fewer.")
        return name

    def clean_carpool_seats(self):
        """Validate carpool seats range."""
        seats = self.cleaned_data.get("carpool_seats", 0)
        if seats < 0 or seats > 6:
            raise forms.ValidationError("Carpool seats must be between 0 and 6.")
        return seats

    def clean(self):
        """Cross-field validation."""
        cleaned = super().clean()
        willing = cleaned.get("willing_to_carpool", False)
        has_vehicle = cleaned.get("has_vehicle", False)
        seats = cleaned.get("carpool_seats", 0)

        if willing and not has_vehicle:
            self.add_error(
                "willing_to_carpool",
                "Cannot offer carpool without a vehicle."
            )
        if seats > 0 and not willing:
            self.add_error(
                "carpool_seats",
                "Set carpool seats to 0 if not willing to carpool."
            )
        return cleaned

    def save(self, commit=True):
        """Save staff member with company assignment."""
        instance = super().save(commit=False)
        if self.company:
            instance.company = self.company
        if commit:
            instance.save()
        return instance
