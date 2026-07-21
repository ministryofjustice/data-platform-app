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
