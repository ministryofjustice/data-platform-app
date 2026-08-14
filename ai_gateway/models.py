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
