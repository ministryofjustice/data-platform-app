from django import forms

from ai_gateway.models import Key
from projects.models import Project


class KeyCreateForm(forms.Form):
    name = forms.CharField(max_length=255, label="Key name")
    models = forms.MultipleChoiceField(label="Models")

    def __init__(self, *args, project: Project, available_models: list[str], **kwargs):
        super().__init__(*args, **kwargs)
        self.project = project
        self.fields["models"].choices = [(model, model) for model in available_models]

    def clean_name(self) -> str:
        name = self.cleaned_data["name"].strip()
        if Key.objects.filter(project=self.project, name=name).exists():
            raise forms.ValidationError("A key with this name already exists for this project.")
        return name
