from __future__ import annotations

from functools import cached_property

from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils.cache import add_never_cache_headers
from django.views.generic import DetailView, FormView, ListView

from ai_gateway.forms import KeyCreateForm
from ai_gateway.services import KeyService
from projects.mixins import ProjectLayoutContextMixin
from projects.models import Project


class ProjectScopedMixin:
    """Resolves the project from the URL, limited to the requesting user's projects."""

    request: HttpRequest
    kwargs: dict

    @cached_property
    def project(self) -> Project:
        return get_object_or_404(
            Project.objects.filter(user_permissions__user=self.request.user).distinct(),
            uuid=self.kwargs["uuid"],
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["project"] = self.project
        return context


class KeyListView(ProjectScopedMixin, ProjectLayoutContextMixin, ListView):
    template_name = "ai_gateway/key-list.html"
    context_object_name = "keys"
    active_project_section = "ai_gateway"

    def get_queryset(self):
        return self.project.ai_gateway_keys.order_by("-created")


class KeyCreateView(ProjectScopedMixin, FormView):
    """Generates a virtual key for a project and renders it from the POST response."""

    template_name = "ai_gateway/key-create.html"
    form_class = KeyCreateForm

    @cached_property
    def available_models(self) -> list[str]:
        with KeyService.from_settings() as service:
            return service.list_default_models()

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["project"] = self.project
        kwargs["available_models"] = self.available_models
        return kwargs

    def form_valid(self, form: KeyCreateForm) -> HttpResponse:
        with KeyService.from_settings() as service:
            plaintext_key = service.create_key(
                project=self.project,
                name=form.cleaned_data["name"],
                models=form.cleaned_data["models"],
                created_by=self.request.user,
            )

        response = render(
            self.request,
            "ai_gateway/key-created.html",
            {"project": self.project, "plaintext_key": plaintext_key},
        )
        add_never_cache_headers(response)
        return response


class KeyDetailView(ProjectScopedMixin, DetailView):
    template_name = "ai_gateway/key-detail.html"
    context_object_name = "key"

    def get_queryset(self):
        return self.project.ai_gateway_keys.all()
