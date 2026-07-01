from django import forms

from projects.models import BusinessUnit


class AddMembersForm(forms.Form):
    """Validates the add-members step of the project creation wizard.

    Handles the yes/no choice, optional email entry, and add-another action.
    Pass existing_members so the form can enforce the per-project limit and
    reject duplicates without the view needing to inspect the session list.
    """

    MAX_MEMBERS = 20

    add_members_now = forms.ChoiceField(
        choices=[("yes", "Yes"), ("no", "No")],
        error_messages={
            "required": "Choose Yes or No",
            "invalid_choice": "Choose Yes or No",
        },
    )
    member_email = forms.EmailField(
        required=False,
        error_messages={"invalid": "Enter a valid email address"},
    )
    action = forms.CharField(required=False)

    def __init__(self, *args, existing_members=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.existing_members = existing_members or []

    def clean_action(self):
        """Normalise unknown action values to 'continue'."""
        value = self.cleaned_data.get("action", "").strip()
        return value if value in {"add_another", "continue"} else "continue"

    def clean(self):
        """
        Apply cross-field rules: action/choice agreement, email presence,
        duplicate, and limit.
        """
        cleaned_data = super().clean()
        add_members_now = cleaned_data.get("add_members_now")
        member_email = cleaned_data.get("member_email", "")
        action = cleaned_data.get("action", "continue")

        if add_members_now is None:
            return cleaned_data

        if action == "add_another" and add_members_now != "yes":
            self.add_error("add_members_now", "Select Yes to add another member")

        if add_members_now == "yes":
            if not member_email:
                self.add_error("member_email", "Enter an email address")
            elif any(m.casefold() == member_email.casefold() for m in self.existing_members):
                self.add_error("member_email", "This member has already been added")
            elif len(self.existing_members) >= self.MAX_MEMBERS:
                self.add_error(
                    "member_email",
                    f"You can only add up to {self.MAX_MEMBERS} members",
                )

        return cleaned_data


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
