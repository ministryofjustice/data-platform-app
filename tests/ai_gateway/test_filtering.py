from ai_gateway.filtering import filter_models

MODELS = [
    {
        "model_name": "gpt-4",
        "display_name": "GPT-4",
        "family": "GPT",
        "provider": "OpenAI",
    },
    {
        "model_name": "gpt-4o-mini",
        "display_name": "GPT-4o mini",
        "family": "GPT",
        "provider": "OpenAI",
    },
    {
        "model_name": "claude-3",
        "display_name": "Claude 3",
        "family": "Claude",
        "provider": "Anthropic",
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
        assert filter_models(MODELS, provider="Non-existent") == []

    def test_no_selected_model_ids_preserves_input_order(self):
        assert filter_models(MODELS, selected_model_ids=[]) == MODELS

    def test_selected_models_move_to_the_front(self):
        result = filter_models(MODELS, selected_model_ids=["claude-3"])

        assert [model["model_name"] for model in result] == [
            "claude-3",
            "gpt-4",
            "gpt-4o-mini",
        ]

    def test_relative_order_is_preserved_within_each_group(self):
        result = filter_models(MODELS, selected_model_ids=["gpt-4o-mini", "claude-3"])

        assert [model["model_name"] for model in result] == [
            "gpt-4o-mini",
            "claude-3",
            "gpt-4",
        ]

    def test_selection_ordering_applies_after_filtering(self):
        result = filter_models(MODELS, family="GPT", selected_model_ids=["gpt-4o-mini"])

        assert [model["model_name"] for model in result] == ["gpt-4o-mini", "gpt-4"]
