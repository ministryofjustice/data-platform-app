import uuid

from django import forms
from django.core.exceptions import ValidationError
from django.forms import BaseFormSet, formset_factory

from projects.models import Project, ProjectUserPermissions


class ProjectAddMemberForm(forms.Form):
    # The visible search box is rendered by the Entra autocomplete component;
    # these hidden fields carry the chosen Entra object id plus a snapshot of
    # the email/name for redisplay and confirmation.
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # MOJ Add Another clones rows and rewrites %index% in data-name/data-id,
        # so the hidden fields must advertise their formset-indexed names.
        formset_prefix = self.prefix.rsplit("-", 1)[0]
        for name in ("oid", "email", "display_name"):
            self.fields[name].widget.attrs.update(
                {
                    "data-name": f"{formset_prefix}-%index%-{name}",
                    "data-id": f"id_{formset_prefix}-%index%-{name}",
                }
            )


class BaseProjectAddMemberFormSet(BaseFormSet):
    def __init__(self, *args, project=None, **kwargs):
        self.project = project
        self.selected_members: list[dict] = []
        super().__init__(*args, **kwargs)

    def clean(self):
        super().clean()

        if any(self.errors):
            return

        selected_members = []
        seen = set()
        for form in self.forms:
            oid = (form.cleaned_data.get("oid") or "").strip()
            if not oid:
                continue
            try:
                uuid.UUID(oid)
            except ValueError as error:
                raise ValidationError("Enter a valid email address") from error
            if oid in seen:
                continue
            seen.add(oid)
            selected_members.append(
                {
                    "oid": oid,
                    "email": (form.cleaned_data.get("email") or "").strip(),
                    "display_name": (form.cleaned_data.get("display_name") or "").strip(),
                }
            )

        if not selected_members:
            raise ValidationError("Enter a valid email address")

        if not self.project:
            self.selected_members = selected_members
            return

        selected_oids = [member["oid"] for member in selected_members]
        existing_memberships = ProjectUserPermissions.objects.filter(
            project=self.project,
            user__oid__in=selected_oids,
        )
        if existing_memberships.exists():
            raise ValidationError(
                "One or more selected users are already members of this project."
            )

        self.selected_members = selected_members


def build_project_add_member_formset(*, project, data=None, initial=None, extra=1):
    formset_class = formset_factory(
        ProjectAddMemberForm,
        formset=BaseProjectAddMemberFormSet,
        extra=extra,
    )

    return formset_class(
        data=data,
        initial=initial,
        prefix="members",
        project=project,
    )


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
