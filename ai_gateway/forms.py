from django import forms

from ai_gateway.models import Key
from projects.models import Project


class KeyCreateForm(forms.Form):
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

    def __init__(self, *args, project: Project, available_models: list[str], **kwargs):
        super().__init__(*args, **kwargs)
        self.project = project
        self.fields["models"].choices = [(model, model) for model in available_models]

    def clean_name(self) -> str:
        name = self.cleaned_data["name"].strip()
        if Key.objects.filter(project=self.project, name=name).exists():
            raise forms.ValidationError("A key with this name already exists for this project.")
        return name
