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
    {
        "model_name": "claude-sonnet",
        "display_name": "Claude Sonnet",
        "provider": "Anthropic",
        "input_cost_per_million": 20.0,
        "output_cost_per_million": 30.0,
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
        "models-MIN_NUM_FORMS": "1",
        "models-MAX_NUM_FORMS": "1000",
    }


class TestAIUsageCostCalculatorForm:
    def test_accepts_valid_model_usage(self):

        form = ModelUsageRateForm(data=calculator_form_data(), available_models=AVAILABLE_MODELS)

        assert form.is_valid()

    def test_rejects_invalid_model_usage(self):

        form = ModelUsageRateForm(
            data=calculator_form_data(model="invalid-model"), available_models=AVAILABLE_MODELS
        )

        assert not form.is_valid()

    def test_requires_model(self):

        form = ModelUsageRateForm(
            data=calculator_form_data(model=""), available_models=AVAILABLE_MODELS
        )

        assert not form.is_valid()
        assert "Select a model" in form.errors["model"]

    def test_requires_requests(self):

        form = ModelUsageRateForm(
            data=calculator_form_data(requests_per_period=""), available_models=AVAILABLE_MODELS
        )

        assert not form.is_valid()
        assert "Enter the number of requests" in form.errors["requests_per_period"]

    @pytest.mark.parametrize(
        "field_name",
        [
            "input_tokens",
            "output_tokens",
            "requests_per_period",
        ],
    )
    def test_accepts_values_above_one_million(self, field_name):
        form_data = calculator_form_data(**{field_name: "1000001"})
        form = ModelUsageRateForm(data=form_data, available_models=AVAILABLE_MODELS)

        assert form.is_valid()

    @pytest.mark.parametrize(
        "field_name", ["input_tokens", "output_tokens", "requests_per_period"]
    )
    def test_rejects_values_that_overflow_the_estimate(self, field_name):
        form = ModelUsageRateForm(
            data=calculator_form_data(**{field_name: "9" * 310}),
            available_models=AVAILABLE_MODELS,
        )

        assert not form.is_valid()
        assert "Enter smaller token or request values" in str(form.non_field_errors())

    def test_rejects_a_non_finite_estimate_from_finite_inputs(self):
        form = ModelUsageRateForm(
            data=calculator_form_data(input_tokens=str(10**200), requests_per_period=str(10**200)),
            available_models=AVAILABLE_MODELS,
        )

        assert not form.is_valid()
        assert form.non_field_errors()

    def test_filters_model_choices_by_selected_provider(self):
        form = ModelUsageRateForm(
            data=calculator_form_data(provider="OpenAI"),
            available_models=AVAILABLE_MODELS,
        )

        assert form.fields["model"].choices == [
            ("gpt-4", "GPT-4"),
        ]


class TestModelUsageRateFormSet:
    def test_rejects_an_overflowing_total_when_individual_rows_are_valid(self):
        models = [
            {
                **AVAILABLE_MODELS[0],
                "input_cost_per_million": 1_000_000.0,
                "output_cost_per_million": 0.0,
            }
        ]
        data = calculator_formset_management_data(total_forms=2)
        for index in range(2):
            data.update(
                {
                    f"models-{index}-{name}": value
                    for name, value in calculator_form_data(
                        input_tokens="1", output_tokens="0", requests_per_period=str(10**308)
                    ).items()
                }
            )
        formset = build_model_usage_rate_formset(data=data, available_models=models)

        assert all(form.is_valid() for form in formset.forms)
        assert not formset.is_valid()
        assert "Enter smaller token or request values" in str(formset.non_form_errors())

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
            data=formset_data, available_models=AVAILABLE_MODELS
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
            data=formset_data, available_models=AVAILABLE_MODELS
        )
        assert not formset.is_valid()

    def test_requires_at_least_one_completed_model_row(self):
        formset = build_model_usage_rate_formset(
            data=calculator_formset_management_data()
            | {
                "models-0-provider": "",
                "models-0-model": "",
                "models-0-input_tokens": "",
                "models-0-output_tokens": "",
                "models-0-requests_per_period": "",
            },
            available_models=AVAILABLE_MODELS,
        )

        assert not formset.is_valid()

    def test_formset_filters_model_choices_by_provider(self):
        formset = build_model_usage_rate_formset(
            data=calculator_formset_management_data()
            | {
                "models-0-provider": "Anthropic",
                "models-0-model": "claude-sonnet",
                "models-0-input_tokens": "1000",
                "models-0-output_tokens": "500",
                "models-0-requests_per_period": "100",
            },
            available_models=AVAILABLE_MODELS,
        )

        assert formset.forms[0].fields["model"].choices == [
            ("claude-sonnet", "Claude Sonnet"),
        ]
