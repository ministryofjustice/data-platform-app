from django import forms

from ai_gateway.models import Key
from projects.models import Project


class KeyCreateForm(forms.Form):
    name = forms.CharField(max_length=255, label="Key name")

    def __init__(self, *args, project: Project, **kwargs):
        super().__init__(*args, **kwargs)
        self.project = project

    def clean_name(self) -> str:
        name = self.cleaned_data["name"].strip()
        if Key.objects.filter(project=self.project, name=name).exists():
            raise forms.ValidationError("A key with this name already exists for this project.")
        return name
