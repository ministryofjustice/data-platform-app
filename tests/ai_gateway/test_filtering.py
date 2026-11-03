from ai_gateway.filtering import exclude_catalogue_models, filter_models

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


class TestExcludeCatalogueModels:
    def test_excludes_nested_account_glob_and_preserves_remaining_order(self):
        models = [
            {"model_name": "first", "litellm_params": {"aws_account_name": "shared"}},
            {
                "model_name": "restricted",
                "litellm_params": {"aws_account_name": "digital-prison-reporting-production"},
            },
            {"model_name": "last"},
        ]
        rules = [
            {"field": "litellm_params.aws_account_name", "pattern": "digital-prison-reporting-*"},
        ]

        assert exclude_catalogue_models(models, rules) == [models[0], models[2]]

    def test_any_matching_rule_excludes_a_model(self):
        models = [
            {"region": "Global"},
            {"model_info": {"region": "us-east-1"}},
            {"region": "United Kingdom"},
        ]
        rules = [
            {"field": "region", "pattern": "Global"},
            {"field": "model_info.region", "pattern": "us-*"},
        ]

        assert exclude_catalogue_models(models, rules) == [models[2]]

    def test_no_rules_keeps_all_models(self):
        assert exclude_catalogue_models(MODELS, []) == MODELS

    def test_missing_and_non_string_fields_do_not_match_wildcards(self):
        models = [{}, {"region": None}, {"region": False}, {"model_info": None}]

        assert exclude_catalogue_models(models, [{"field": "region", "pattern": "*"}]) == models


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

    def test_filters_by_region(self):
        models = [
            {**MODELS[0], "region": "United Kingdom"},
            {**MODELS[1], "region": "European Union"},
        ]

        result = filter_models(models, region="European Union")

        assert [model["model_name"] for model in result] == ["gpt-4o-mini"]

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
