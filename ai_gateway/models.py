from django.db import models
from django_extensions.db.models import TimeStampedModel
from simple_history.models import HistoricalRecords

from ai_gateway.fields import EncryptedTextField


class Team(TimeStampedModel):
    project = models.OneToOneField(
        "projects.Project",
        on_delete=models.CASCADE,
        related_name="ai_gateway_team",
    )
    litellm_team_id = models.CharField(max_length=255, unique=True)
    history = HistoricalRecords(table_name="ai_gateway_team_history")

    class Meta:
        db_table = "ai_gateway_team"

    def __str__(self) -> str:
        return f"AI Gateway team for {self.project.name}"


class KeyHistoricalModel(models.Model):
    class Meta:
        abstract = True

    def _changes(self, source: list[str], comparison: list[str]) -> list:
        """Return sorted items present in source but not comparison."""
        changes = list(set(source) - set(comparison))
        changes.sort()
        return changes

    @property
    def models_added(self) -> list:
        if self.history_type == "+":
            return self.models

        if not self.prev_record:
            return []
        return self._changes(source=self.models, comparison=self.prev_record.models)

    @property
    def models_removed(self) -> list:
        if not self.prev_record:
            return []
        return self._changes(source=self.prev_record.models, comparison=self.models)

    @property
    def has_models_added_and_removed(self) -> bool:
        return bool(self.models_added and self.models_removed)

    @property
    def has_model_changes(self) -> bool:
        return bool(self.models_added or self.models_removed)

    @property
    def model_change_type(self) -> str | None:
        if self.history_type == "+":
            return "Key created"
        if self.has_models_added_and_removed:
            return "Model changed"
        if self.models_added:
            return "Model added"
        if self.models_removed:
            return "Model removed"
        return None


class Key(TimeStampedModel):
    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.CASCADE,
        related_name="ai_gateway_keys",
    )
    name = models.CharField(max_length=255)
    litellm_secret = EncryptedTextField()
    litellm_alias = models.CharField(max_length=512, unique=True)
    litellm_token = models.CharField(max_length=255)
    masked_key = models.CharField(max_length=64)
    created_by = models.ForeignKey(
        "users.User",
        on_delete=models.SET_NULL,
        null=True,
    )
    models = models.JSONField(
        default=list,
        help_text=(
            "Model identifiers last successfully applied by this application. "
            "Only changes made through this application are captured; "
            "the AI Gateway remains the source of truth."
        ),
    )
    history = HistoricalRecords(
        bases=(KeyHistoricalModel,),
        table_name="ai_gateway_key_history",
        excluded_fields=["litellm_secret"],
    )

    class Meta:
        db_table = "ai_gateway_key"
        constraints = [
            models.UniqueConstraint(
                fields=["project", "name"],
                name="ai_gateway_key_project_name_uniq",
            )
        ]

    def __str__(self) -> str:
        return self.name
