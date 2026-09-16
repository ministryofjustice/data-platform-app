import uuid

from django import forms
from django.core.exceptions import ValidationError

from projects.models import Project, ProjectMembership, ProjectPermission


class ProjectMemberForm(forms.Form):
    """A single project member plus the permissions to grant them.

    The visible search box is rendered by the Entra autocomplete component;
    these hidden fields carry the chosen Entra object id plus a snapshot of
    the email/name for redisplay and confirmation.
    """

    oid = forms.CharField(
        required=False,
        widget=forms.HiddenInput(attrs={"data-entra-user-id": ""}),
    )
    email = forms.CharField(
        required=False,
        widget=forms.HiddenInput(attrs={"data-entra-user-email": ""}),
    )
    display_name = forms.CharField(
        required=False,
        widget=forms.HiddenInput(attrs={"data-entra-user-name": ""}),
    )
    permissions = forms.MultipleChoiceField(
        label="Permissions",
        required=False,
        choices=ProjectPermission.choices,
        initial=list,
        widget=forms.CheckboxSelectMultiple(attrs={"class": "govuk-checkboxes__input"}),
    )

    def __init__(
        self,
        *args,
        existing_oids: set[str] | None = None,
        editing_oid: str | None = None,
        project: Project | None = None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.existing_oids = existing_oids or set()
        self.editing_oid = editing_oid
        self.project = project

    def clean_oid(self) -> str:
        oid = (self.cleaned_data.get("oid") or "").strip()
        if not oid:
            raise ValidationError("Search for and select a project member")
        try:
            # Canonicalise so downstream lookups keyed on str(user.oid) match.
            return str(uuid.UUID(oid))
        except ValueError as error:
            raise ValidationError("Enter a valid email address") from error

    def clean(self):
        cleaned_data = super().clean()
        oid = cleaned_data.get("oid")
        if not oid:
            return cleaned_data

        if oid in self.existing_oids and oid != self.editing_oid:
            self.add_error("oid", "This person has already been added")
            return cleaned_data

        if (
            self.project
            and ProjectMembership.objects.filter(project=self.project, user__oid=oid).exists()
        ):
            self.add_error("oid", "This person is already a member of this project")

        return cleaned_data


class ProjectCreateForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["business_unit"].empty_label = "No business unit selected"

    class Meta:
        model = Project
        fields = ["name", "business_unit", "description"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "govuk-input"}),
            "description": forms.Textarea(attrs={"class": "govuk-textarea", "rows": 5}),
            "business_unit": forms.Select(attrs={"class": "govuk-select"}),
        }
        labels = {
            "business_unit": "Business unit",
        }
        error_messages = {
            "name": {
                "required": "Enter a project name",
            },
            "description": {
                "required": "Enter a description",
            },
            "business_unit": {
                "required": "Select a business unit",
            },
        }


class ProjectCreateAddUsersDecisionForm(forms.Form):
    add_user = forms.ChoiceField(
        label="Do you want to add project members now?",
        choices=(("yes", "Yes"), ("no", "No")),
        widget=forms.RadioSelect,
        error_messages={
            "required": "Choose yes or no",
        },
    )
