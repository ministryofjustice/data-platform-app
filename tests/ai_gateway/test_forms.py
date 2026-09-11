import pytest

from ai_gateway.forms import ModelUsageRateForm, build_model_usage_rate_formset


AVAILABLE_MODELS = [
    {
        "model_name": "gpt-4",
        "display_name": "GPT-4",
        "provider": "OpenAI",
        "input_cost_per_million": 30.0,
        "output_cost_per_million": 60.0,
    },
]

def calculator_form_data(**overrides):
    data = {
        "provider": "OpenAI",
        "model": "gpt-4",
        "input_tokens": "1000",
        "output_tokens": "500",
        "requests_per_period": "100",
    }

    return data | overrides

def calculator_formset_management_data(total_forms=1):
    return {
        "models-TOTAL_FORMS": str(total_forms),
        "models-INITIAL_FORMS": "0",
        "models-MIN_NUM_FORMS": "0",
        "models-MAX_NUM_FORMS": "1000",
    }

class TestAIUsageCostCalculatorForm:

    def test_accepts_valid_model_usage(self):

        form = ModelUsageRateForm(
            data=calculator_form_data(),
            available_models=AVAILABLE_MODELS
        )

        assert form.is_valid()

    def test_rejects_invalid_model_usage(self):

        form = ModelUsageRateForm(
            data=calculator_form_data(model="invalid-model"),
            available_models=AVAILABLE_MODELS
        )

        assert not form.is_valid()

    def test_requires_model(self):

        form = ModelUsageRateForm(
            data=calculator_form_data(model=""),
            available_models=AVAILABLE_MODELS
        )

        assert not form.is_valid()
        assert "Select a model" in form.errors["model"]

    def test_requires_requests(self):

        form = ModelUsageRateForm(
            data=calculator_form_data(requests_per_period=""),
            available_models=AVAILABLE_MODELS
        )

        assert not form.is_valid()
        assert "Enter the number of requests" in form.errors["requests_per_period"]

    @pytest.mark.parametrize(
        "field_name",
        [
            "input_tokens",
            "output_tokens",
            "requests_per_period",
        ]
    )

    def test_rejects_values_above_one_million(self, field_name):
        form_data = calculator_form_data(**{field_name: "1000001"})
        form = ModelUsageRateForm(
            data=form_data,
            available_models=AVAILABLE_MODELS
        )

        assert not form.is_valid()
        assert "Ensure this value is less than or equal to 1000000."


class TestModelUsageRateFormSet:
    def test_formset_accepts_valid_data(self):
        management_data = calculator_formset_management_data(total_forms=1)
        form_data = {
            "models-0-provider": "OpenAI",
            "models-0-model": "gpt-4",
            "models-0-input_tokens": "1000",
            "models-0-output_tokens": "500",
            "models-0-requests_per_period": "100",
        }
        formset_data = management_data | form_data
        formset = build_model_usage_rate_formset(
            data=formset_data,
            available_models=AVAILABLE_MODELS
        )
        assert formset.is_valid()

    def test_formset_rejects_invalid_data(self):
        management_data = calculator_formset_management_data(total_forms=1)
        form_data = {
            "models-0-provider": "OpenAI",
            "models-0-model": "invalid-model",
            "models-0-input_tokens": "1000",
            "models-0-output_tokens": "500",
            "models-0-requests_per_period": "100",
        }
        formset_data = management_data | form_data
        formset = build_model_usage_rate_formset(
            data=formset_data,
            available_models=AVAILABLE_MODELS
        )
        assert not formset.is_valid()

    def test_requires_at_least_one_completed_model_row(self):
        formset = build_model_usage_rate_formset(
            data=calculator_formset_management_data() | {
                "models-0-provider": "",
                "models-0-model": "",
                "models-0-input_tokens": "",
                "models-0-output_tokens": "",
                "models-0-requests_per_period": "",
            },
            available_models=AVAILABLE_MODELS
        )

        assert not formset.is_valid()
        assert "Select a model"
