from ai_gateway.filtering import filter_models, model_display_name

MODELS = [
    {
        "model_name": "gpt-4",
        "litellm_params": {
            "ai_model_name": "GPT-4",
            "ai_model_family": "GPT",
            "ai_model_provider": "OpenAI",
        },
    },
    {
        "model_name": "gpt-4o-mini",
        "litellm_params": {
            "ai_model_name": "GPT-4o mini",
            "ai_model_family": "GPT",
            "ai_model_provider": "OpenAI",
        },
    },
    {
        "model_name": "claude-3",
        "litellm_params": {
            "ai_model_name": "Claude 3",
            "ai_model_family": "Claude",
            "ai_model_provider": "Anthropic",
        },
    },
]


class TestFilterModels:
    def test_no_filters_returns_all_in_order(self):
        assert filter_models(MODELS) == MODELS

    def test_search_matches_display_name_case_insensitively(self):
        result = filter_models(MODELS, search="CLAUDE")

        assert [model["model_name"] for model in result] == ["claude-3"]

    def test_search_matches_a_partial_name(self):
        result = filter_models(MODELS, search="4o")

        assert [model["model_name"] for model in result] == ["gpt-4o-mini"]

    def test_filters_by_provider(self):
        result = filter_models(MODELS, provider="Anthropic")

        assert [model["model_name"] for model in result] == ["claude-3"]

    def test_filters_by_family(self):
        result = filter_models(MODELS, family="GPT")

        assert [model["model_name"] for model in result] == ["gpt-4", "gpt-4o-mini"]

    def test_combines_all_filters(self):
        result = filter_models(MODELS, search="mini", provider="OpenAI", family="GPT")

        assert [model["model_name"] for model in result] == ["gpt-4o-mini"]

    def test_no_matches_returns_empty_list(self):
        assert filter_models(MODELS, provider="Nonexistent") == []


class TestModelDisplayName:
    def test_prefers_the_configured_display_name(self):
        assert model_display_name(MODELS[0]) == "GPT-4"

    def test_falls_back_to_the_model_name(self):
        assert model_display_name({"model_name": "bare-model"}) == "bare-model"
