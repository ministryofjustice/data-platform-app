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
    history = HistoricalRecords(table_name="data_platform_app_project_user_permissions_history")

    class Meta:
        db_table = "data_platform_app_project_user_permissions"
        verbose_name_plural = "project user permissions"


class BusinessUnit(TimeStampedModel):
    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=20, unique=True)

    def __str__(self):
        return self.name


class Project(TimeStampedModel):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField()
    slug = models.SlugField(unique=True)
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

    def __str__(self):
        return self.name


class ProjectMember(TimeStampedModel):
    project = models.ForeignKey("Project", on_delete=models.CASCADE, related_name="member_emails")
    email = models.EmailField()
    user = models.ForeignKey(
        "users.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="project_member_records",
    )

    class Meta:
        db_table = "data_platform_app_project_member"
        constraints = [
            models.UniqueConstraint(fields=["project", "email"], name="unique_project_member")
        ]

    def __str__(self):
        return self.email
