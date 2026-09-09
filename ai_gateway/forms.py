from datetime import date, datetime
from typing import Any

from django import forms
from django.forms import BaseFormSet, formset_factory

from ai_gateway.models import Key
from projects.models import Project


def _parse_usage_month(value: str) -> date:
    """Convert a form choice in ``YYYY-MM`` format to the first of its month."""
    return datetime.strptime(value, "%Y-%m").date().replace(day=1)


class UsageMonthForm(forms.Form):
    """Validate a usage month against choices supplied by ``UsageService``."""

    month = forms.TypedChoiceField(required=False, coerce=_parse_usage_month)

    def __init__(self, *args, month_choices: list[date], **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fields["month"].choices = [
            (month.strftime("%Y-%m"), month.strftime("%B %Y")) for month in month_choices
        ]


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


class UsagePeriodForm(forms.Form):
    """The Daily/Monthly choice for the AI usage cost calculator."""

    PERIOD_CHOICES = [("daily", "Daily"), ("monthly", "Monthly")]

    usage_period = forms.ChoiceField(
        choices=PERIOD_CHOICES,
        widget=forms.RadioSelect,
        initial="monthly",
        error_messages={"required": "Select a usage period"},
    )


class ModelUsageRateForm(forms.Form):
    """One model row in the AI usage cost calculator: a model plus its expected usage."""

    provider = forms.ChoiceField(
        error_messages={"required": "Select a provider"},
    )
    model = forms.ChoiceField(
        error_messages={"required": "Select a model"},
    )
    input_tokens = forms.IntegerField(
        label="Input tokens",
        min_value=0,
        max_value=1000000,
        error_messages={"required": "Enter the number of input tokens"},
    )
    output_tokens = forms.IntegerField(
        label="Output tokens",
        min_value=0,
        max_value=1000000,
        error_messages={"required": "Enter the number of output tokens"},
    )
    requests_per_period = forms.IntegerField(
        label="Requests",
        min_value=0,
        max_value=1000000,
        error_messages={"required": "Enter the number of requests"},
    )

    def __init__(self, *args, available_models: list[dict[str, Any]], **kwargs):
        super().__init__(*args, **kwargs)
        self.available_models = available_models
        self.fields["provider"].choices = sorted(
            {(model["provider"], model["provider"]) for model in available_models}
        )
        self.fields["model"].choices = [
            (model["model_name"], model["display_name"]) for model in available_models
        ]


class BaseModelUsageRateFormSet(BaseFormSet):
    def __init__(self, *args, available_models: list[dict[str, Any]], **kwargs):
        self.available_models = available_models
        super().__init__(*args, **kwargs)

    def get_form_kwargs(self, index):
        kwargs = super().get_form_kwargs(index)
        kwargs["available_models"] = self.available_models
        return kwargs

    def clean(self):
        super().clean()

        if any(self.errors):
            return

        if not any(form.has_changed() for form in self.forms):
            raise forms.ValidationError("Add at least one model")


def build_model_usage_rate_formset(*, available_models, data=None, initial=None, extra=1):
    formset_class = formset_factory(
        ModelUsageRateForm,
        formset=BaseModelUsageRateFormSet,
        extra=extra,
    )

    return formset_class(
        data=data,
        initial=initial,
        prefix="models",
        available_models=available_models,
    )
