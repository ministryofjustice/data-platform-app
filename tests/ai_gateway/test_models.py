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
