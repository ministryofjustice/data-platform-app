from collections import Counter

from django import forms
from django.core.exceptions import ValidationError
from django.forms import BaseFormSet, formset_factory

from projects.models import ProjectUserPermissions
from users.models import User


class ProjectAddMemberForm(forms.Form):
    user = forms.ModelChoiceField(
        queryset=User.objects.none(),
        label="Email address",
        required=False,
        empty_label="Select an email address",
    )

    def __init__(self, *args, project, **kwargs):
        super().__init__(*args, **kwargs)
        self.project = project
        self.fields["user"].queryset = (
            User.objects.exclude(
                projects=self.project,
            )
            .exclude(
                email="",
            )
            .order_by("email")
            .distinct()
        )
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
    def __init__(self, *args, project, **kwargs):
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
            raise ValidationError("Select at least one user to continue.")

        duplicate_user_ids = [
            user_id for user_id, count in Counter(selected_user_ids).items() if count > 1
        ]
        if duplicate_user_ids:
            raise ValidationError("You cannot add the same user more than once.")

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
