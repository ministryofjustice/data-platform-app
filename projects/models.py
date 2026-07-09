import uuid

from django.db import models
from django_extensions.db.models import TimeStampedModel
from simple_history.models import HistoricalRecords

# Create your models here.


class ProjectUserPermissions(TimeStampedModel):
    project = models.ForeignKey(
        "Project", on_delete=models.CASCADE, related_name="user_permissions"
    )
    user = models.ForeignKey("users.User", on_delete=models.CASCADE)
    role = models.CharField(max_length=30)
    history = HistoricalRecords(table_name="user_permissions_history")

    class Meta:
        db_table = "project_user_permissions"
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


class Project(TimeStampedModel):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField()
    slug = models.SlugField(max_length=120, unique=True)
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)
    users = models.ManyToManyField(
        "users.User",
        related_name="projects",
        through=ProjectUserPermissions,
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

    @property
    def public_id(self) -> str:
        return f"prj-{self.uuid}"

    @staticmethod
    def get_by_public_id(public_id: str) -> "Project":
        if not public_id.startswith("prj-"):
            raise ValueError("Invalid public ID format")
        uuid_str = public_id[4:]
        try:
            project_uuid = uuid.UUID(uuid_str)
        except ValueError as err:
            raise ValueError("Invalid UUID in public ID") from err
        return Project.objects.get(uuid=project_uuid)
