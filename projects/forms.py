from django import forms

from projects.models import BusinessUnit


class ProjectCreateForm(forms.Form):
    """Validates the first step of the project creation wizard.

    Handles name, business unit, and description.  Validation rules are
    declared on each field so the view only needs to call is_valid().
    """

    name = forms.CharField(
        strip=True,
        error_messages={"required": "Enter a project name"},
    )
    business_unit = forms.ChoiceField(
        choices=(),
        error_messages={
            "required": "Select a business unit",
            "invalid_choice": "Select a valid business unit",
        },
    )
    description = forms.CharField(
        strip=True,
        widget=forms.Textarea,
        error_messages={"required": "Enter a description"},
    )

    def __init__(self, *args, **kwargs):
        """Populate business unit choices from the database."""
        super().__init__(*args, **kwargs)
        business_units = BusinessUnit.objects.order_by("name").values_list("name", flat=True)
        self.fields["business_unit"].choices = [("", "No business unit selected")] + [
            (business_unit, business_unit) for business_unit in business_units
        ]
