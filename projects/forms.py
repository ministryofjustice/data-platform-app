from collections import Counter

from django import forms
from django.core.exceptions import ValidationError
from django.forms import BaseFormSet, formset_factory

from projects.models import Project, ProjectUserPermissions
from users.models import User


class ProjectAddMemberForm(forms.Form):
    user = forms.ModelChoiceField(
        queryset=User.objects.none(),
        label="Email address",
        required=False,
        empty_label="Select an email address",
    )

    def __init__(self, *args, project=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.project = project
        queryset = User.objects.exclude(email="").order_by("email").distinct()
        if self.project is not None:
            queryset = queryset.exclude(projects=self.project)

        self.fields["user"].queryset = queryset
        self.fields["user"].label_from_instance = lambda user: user.email

        prefix_template = "members-%index%"
        if self.prefix and "-" in self.prefix:
            prefix_template = f"{self.prefix.rsplit('-', 1)[0]}-%index%"

        self.fields["user"].widget.attrs.update(
            {
                "class": "govuk-select",
                "data-module": "autocomplete",
                "data-autoselect": "false",
                "data-show-all-values": "false",
                "data-min-length": "2",
                "data-show-no-options-found": "true",
                "data-name": f"{prefix_template}-user",
                "data-id": f"id_{prefix_template}-user",
            }
        )


class BaseProjectAddMemberFormSet(BaseFormSet):
    def __init__(self, *args, project=None, **kwargs):
        self.project = project
        self.selected_user_ids: list[int] = []
        super().__init__(*args, **kwargs)

    def clean(self):
        super().clean()

        if any(self.errors):
            return

        selected_user_ids = []
        for form in self.forms:
            user = form.cleaned_data.get("user")
            if user:
                selected_user_ids.append(user.id)

        if not selected_user_ids:
            raise ValidationError("Enter a valid email address")

        duplicate_user_ids = [
            user_id for user_id, count in Counter(selected_user_ids).items() if count > 1
        ]
        if duplicate_user_ids:
            raise ValidationError("You cannot add the same user more than once.")

        if self.project is not None:
            existing_memberships = ProjectUserPermissions.objects.filter(
                project=self.project,
                user_id__in=selected_user_ids,
            )
            if existing_memberships.exists():
                raise ValidationError(
                    "One or more selected users are already members of this project."
                )

        self.selected_user_ids = selected_user_ids


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
        form_kwargs={"project": project},
        project=project,
    )


class ProjectCreateForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["business_unit"].empty_label = "Select a business unit"

    class Meta:
        model = Project
        fields = ["name", "description", "business_unit"]
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
