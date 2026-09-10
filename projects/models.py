import uuid

from django.db import models
from django.urls import reverse
from django_extensions.db.models import TimeStampedModel
from simple_history.models import HistoricalRecords


class ProjectPermission(models.TextChoices):
    MANAGE_API_KEYS = "manage_api_keys", "Manage API Keys"
    MANAGE_MEMBERS = "manage_members", "Manage Members"


class ProjectMembershipPermission(TimeStampedModel):
    membership = models.ForeignKey(
        "ProjectMembership", on_delete=models.CASCADE, related_name="permissions"
    )
    permission = models.CharField(
        max_length=50,
        choices=ProjectPermission.choices,
    )
    granted_by = models.ForeignKey(
        "users.User",
        on_delete=models.SET_NULL,
        null=True,
        related_name="granted_project_permissions",
    )
    history = HistoricalRecords(table_name="project_membership_permission_history")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["membership", "permission"],
                name="uniq_project_membership_permission",
            )
        ]


class ProjectMembership(TimeStampedModel):
    project = models.ForeignKey(
        "Project", on_delete=models.CASCADE, related_name="user_permissions"
    )
    user = models.ForeignKey("users.User", on_delete=models.CASCADE)
    history = HistoricalRecords(table_name="project_membership_history")

    class Meta:
        db_table = "project_membership"
        verbose_name_plural = "project user permissions"
        constraints = [
            models.UniqueConstraint(
                fields=["project", "user"],
                name="uniq_project_user_membership",
            )
        ]


class BusinessUnit(TimeStampedModel):
    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=20, unique=True)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ["name"]


class Project(TimeStampedModel):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField()
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)
    users = models.ManyToManyField(
        "users.User",
        related_name="projects",
        through=ProjectMembership,
        through_fields=("project", "user"),
    )
    business_unit = models.ForeignKey(
        BusinessUnit, on_delete=models.CASCADE, related_name="projects"
    )
    created_by = models.ForeignKey(
        "users.User",
        on_delete=models.SET_NULL,
        null=True,
    )

    history = HistoricalRecords(table_name="project_history")

    def __str__(self):
        return self.name

    def get_absolute_url(self) -> str:
        return reverse(viewname="projects:project_detail", kwargs={"uuid": self.uuid})

    def get_absolute_keys_url(self) -> str:
        return reverse(viewname="ai_gateway:key_list", kwargs={"uuid": self.uuid})
