from ai_gateway.forms import KeyCreateForm, KeyModelFilterForm


class TestKeyCreateForm:
    def test_builds_model_choices_from_model_info_records(self):
        form = KeyCreateForm(
            project=object(),
            available_models=[
                {
                    "model_name": "bedrock-claude-sonnet-5",
                    "litellm_params": {
                        "ai_model_name": "Anthropic Claude Sonnet 5 (EU)",
                        "ai_model_provider": "Amazon Bedrock",
                    },
                },
                {
                    "model_name": "gpt-4.1",
                    "litellm_params": {},
                },
            ],
        )

        assert form.fields["models"].choices == [
            ("bedrock-claude-sonnet-5", "Anthropic Claude Sonnet 5 (EU)"),
            ("gpt-4.1", "gpt-4.1"),
        ]

    def test_ignores_records_without_model_name(self):
        form = KeyCreateForm(
            project=object(),
            available_models=[
                {
                    "litellm_params": {
                        "ai_model_name": "missing-model-name",
                        "ai_model_provider": "Unknown",
                    },
                }
            ],
        )

        assert form.fields["models"].choices == []


class TestKeyModelFilterForm:
    def test_filters_by_name_and_provider(self):
        models = [
            {
                "model_name": "gpt-4",
                "litellm_params": {
                    "ai_model_name": "GPT-4",
                    "ai_model_provider": "OpenAI",
                },
            },
            {
                "model_name": "claude-3",
                "litellm_params": {
                    "ai_model_name": "Claude 3",
                    "ai_model_provider": "Anthropic",
                },
            },
        ]
        form = KeyModelFilterForm(
            {"model_name": "claude", "model_provider": "anthropic"},
            provider_choices=["Anthropic", "OpenAI"],
        )

        filtered = form.filter_models(models)

        assert filtered == [
            {
                "model_name": "claude-3",
                "litellm_params": {
                    "ai_model_name": "Claude 3",
                    "ai_model_provider": "Anthropic",
                },
            }
        ]

    def test_returns_all_models_when_provider_is_invalid(self):
        models = [
            {
                "model_name": "gpt-4",
                "litellm_params": {
                    "ai_model_name": "GPT-4",
                    "ai_model_provider": "OpenAI",
                },
            }
        ]
        form = KeyModelFilterForm(
            {"model_provider": "not-a-provider"},
            provider_choices=["OpenAI"],
        )

        assert form.filter_models(models) == models
