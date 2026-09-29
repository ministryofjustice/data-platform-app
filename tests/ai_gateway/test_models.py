class TestKeyModelHistory:
    def test_retains_models_when_key_is_deleted(self, key):
        key.models = ["gpt-4", "claude-3"]
        key.save(update_fields=["models", "modified"])
        key_id = key.pk
        history_model = key.history.model

        key.delete()

        deletion_history = history_model.objects.filter(id=key_id).latest()
        assert deletion_history.history_type == "-"
        assert deletion_history.models == ["gpt-4", "claude-3"]


class TestKeyHistoricalModel:
    def test_models_added(self, key):
        key.models = ["gpt-4"]
        key.save()
        key.models = ["gpt-4", "claude-3"]
        key.save()
        history_model = key.history.model
        latest_history = history_model.objects.filter(id=key.pk).latest()

        assert latest_history.models_added == ["claude-3"]
        assert latest_history.models_removed == []
        assert latest_history.has_models_added_and_removed is False
        assert latest_history.has_model_changes is True

    def test_models_removed(self, key):
        key.models = ["gpt-4", "claude-3"]
        key.save()
        key.models = ["gpt-4"]
        key.save()
        history_model = key.history.model
        latest_history = history_model.objects.filter(id=key.pk).latest()

        assert latest_history.models_added == []
        assert latest_history.models_removed == ["claude-3"]
        assert latest_history.has_models_added_and_removed is False
        assert latest_history.has_model_changes is True

    def test_models_added_and_removed(self, key):
        key.models = ["gpt-4"]
        key.save()
        key.models = ["claude-3"]
        key.save()
        history_model = key.history.model
        latest_history = history_model.objects.filter(id=key.pk).latest()

        assert latest_history.models_added == ["claude-3"]
        assert latest_history.models_removed == ["gpt-4"]
        assert latest_history.has_models_added_and_removed is True
        assert latest_history.has_model_changes is True

    def test_models_sorted(self, key):
        key.models = ["gpt-4", "foundry-1"]
        key.save()
        key.models = ["gemini-2", "claude-3"]
        key.save()
        history_model = key.history.model
        latest_history = history_model.objects.filter(id=key.pk).latest()

        assert latest_history.models_added == ["claude-3", "gemini-2"]
        assert latest_history.models_removed == ["foundry-1", "gpt-4"]
        assert latest_history.has_models_added_and_removed is True
        assert latest_history.has_model_changes is True

    def test_model_change_type(self, key):
        history_model = key.history.model
        latest_history = history_model.objects.filter(id=key.pk).latest()
        assert latest_history.model_change_type == "Key created"

        key.models = ["gpt-4"]
        key.save()
        key.models = ["claude-3"]
        key.save()
        latest_history = history_model.objects.filter(id=key.pk).latest()

        assert latest_history.model_change_type == "Models changed"

        key.models = ["claude-3", "gemini-2"]
        key.save()
        latest_history = history_model.objects.filter(id=key.pk).latest()

        assert latest_history.model_change_type == "Models added"

        key.models = ["gemini-2"]
        key.save()
        latest_history = history_model.objects.filter(id=key.pk).latest()

        assert latest_history.model_change_type == "Models removed"

        key.models = ["gemini-2"]
        key.save()
        latest_history = history_model.objects.filter(id=key.pk).latest()

        assert latest_history.model_change_type is None
