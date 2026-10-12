from django.conf import settings
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVectorField
from django.db import models


class GuideChunk(models.Model):
    """A section of the user guide, indexed for full-text search."""

    source_path = models.CharField(max_length=500)
    position = models.PositiveIntegerField()
    page_title = models.CharField(max_length=500)
    heading = models.CharField(max_length=500)
    url = models.URLField(max_length=1000)
    content = models.TextField()
    search_vector = SearchVectorField(null=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["source_path", "position"]
        constraints = [
            models.UniqueConstraint(
                fields=["source_path", "position"], name="unique_guide_chunk_position"
            ),
        ]
        indexes = [GinIndex(fields=["search_vector"], name="guide_chunk_search_idx")]

    def __str__(self):
        return f"{self.page_title}: {self.heading}"


class Interaction(models.Model):
    """A question asked of the support assistant and the response it gave."""

    class Outcome(models.TextChoices):
        ANSWERED = "answered", "Answered"
        NO_MATCH = "no_match", "No matching guide content"
        DECLINED = "declined", "Model declined to answer"
        ERROR = "error", "Gateway error"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="support_interactions",
    )
    question = models.TextField()
    answer = models.TextField(blank=True)
    outcome = models.CharField(max_length=20, choices=Outcome.choices)
    sources = models.JSONField(
        default=list, blank=True, help_text="Guide sections shown to the user as sources."
    )
    retrieved_chunks = models.JSONField(
        default=list, blank=True, help_text="Guide sections retrieved and sent to the model."
    )
    model = models.CharField(max_length=200, blank=True)
    latency_ms = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_outcome_display()} at {self.created_at:%Y-%m-%d %H:%M}"

    @property
    def is_answered(self) -> bool:
        return self.outcome == self.Outcome.ANSWERED


class Feedback(models.Model):
    """A user's rating of a support assistant answer."""

    interaction = models.OneToOneField(
        Interaction, on_delete=models.CASCADE, related_name="feedback"
    )
    helpful = models.BooleanField()
    comment = models.TextField(blank=True, max_length=1000)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return "Helpful" if self.helpful else "Not helpful"
