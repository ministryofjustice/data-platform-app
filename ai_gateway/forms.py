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
        choices: list[tuple[str, str]] = []
        for model in available_models:
            model_name = model.get("model_name")
            if not model_name:
                continue

            litellm_params = model.get("litellm_params", {})
            label = litellm_params.get("ai_model_name") or model_name

            choices.append((model_name, label))

        self.fields["models"].choices = choices

    def clean_name(self) -> str:
        name = self.cleaned_data["name"].strip()
        if Key.objects.filter(project=self.project, name=name).exists():
            raise forms.ValidationError("A key with this name already exists for this project.")
        return name


class KeyModelFilterForm(forms.Form):
    """Parse and apply model filters from query parameters."""

    model_name = forms.CharField(required=False)
    model_provider = forms.CharField(required=False)

    def __init__(self, *args, provider_choices: list[str], **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["model_provider"] = forms.ChoiceField(
            required=False,
            choices=[("", "All providers")]
            + [(provider.lower(), provider) for provider in provider_choices],
        )

    def filter_models(self, models: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Return models that match current form filters."""
        if not self.is_valid():
            return models

        name_query = self.cleaned_data["model_name"].strip().lower()
        provider_query = self.cleaned_data["model_provider"]

        filtered_models = models
        if name_query:
            filtered_models = [
                model
                for model in filtered_models
                if name_query
                in (
                    model.get("litellm_params", {}).get("ai_model_name")
                    or model.get("model_name", "")
                ).lower()
            ]

        if provider_query:
            filtered_models = [
                model
                for model in filtered_models
                if model.get("litellm_params", {}).get("ai_model_provider", "").lower()
                == provider_query
            ]

        return filtered_models
