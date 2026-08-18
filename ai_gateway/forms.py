from typing import Any

from django import forms

from ai_gateway.models import Key
from projects.models import Project


class KeyCreateForm(forms.ModelForm):
    models = forms.MultipleChoiceField(
        label="AI Model",
        help_text="Add models for this project",
        error_messages={"required": "Select at least one AI model to continue"},
    )
    name = forms.CharField(
        max_length=255,
        label="Key name",
        help_text="Enter a name for the key",
        error_messages={"required": "Enter a key name"},
    )

    class Meta:
        model = Key
        fields = ["name"]

    def __init__(
        self,
        *args,
        project: Project,
        available_models: list[dict[str, Any]],
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.project = project
        self.fields["models"].choices = [
            (model["model_name"], model["display_name"]) for model in available_models
        ]

    def clean_name(self) -> str:
        name = self.cleaned_data["name"].strip()
        if Key.objects.filter(project=self.project, name=name).exists():
            raise forms.ValidationError("A key with this name already exists for this project.")
        return name


class KeyModelChangeForm(forms.Form):
    models = forms.MultipleChoiceField(
        label="AI Model",
        help_text="Add models for this project",
        error_messages={"required": "Select at least one AI model to continue"},
    )

    def __init__(
        self,
        *args,
        available_models: list[dict[str, Any]],
        current_models: set[str] | None = None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.current_models = current_models or set()
        self.fields["models"].choices = [
            (model["model_name"], model["display_name"]) for model in available_models
        ]

    def clean_models(self) -> list[str]:
        selected_models = self.cleaned_data["models"]
        if not selected_models:
            return selected_models

        if set(selected_models) == set(self.current_models):
            raise forms.ValidationError("Make changes to continue")

        return selected_models
