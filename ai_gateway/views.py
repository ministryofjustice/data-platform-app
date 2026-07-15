from __future__ import annotations

from functools import cached_property

from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils.cache import add_never_cache_headers
from django.views.generic import FormView, ListView, TemplateView

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


class KeyListView(ProjectScopedMixin, ProjectLayoutContextMixin, ListView):
    template_name = "ai_gateway/key-list.html"
    context_object_name = "keys"
    active_project_section = "ai_gateway"

    def get_queryset(self):
        return self.project.ai_gateway_keys.order_by("-created")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["project"] = self.project
        return context


class KeyCreateView(ProjectScopedMixin, FormView):
    """Generates a virtual key for a project and renders it from the POST response."""

    template_name = "ai_gateway/key-create.html"
    form_class = KeyCreateForm

    @cached_property
    def available_models(self) -> list[str]:
        with KeyService.from_settings() as service:
            return service.list_default_models()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["project"] = self.project
        return context

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


class KeyRegenerateView(ProjectScopedMixin, TemplateView):
    template_name = "ai_gateway/key-regenerate.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["project"] = self.project
        context["key_name"] = self.kwargs["key_name"]
        return context

    def post(self, request, *args, **kwargs):
        key_name = kwargs["key_name"]
        existing_key = self.project.ai_gateway_keys.get(name=key_name)

        with KeyService.from_settings() as service:
            plaintext_key = service.regenerate_key(
                project=self.project,
                name=existing_key.name,
                key=existing_key.litellm_secret,
            )

        response = render(
            request,
            "ai_gateway/key-created.html",
            {"project": self.project, "plaintext_key": plaintext_key, "regenerated": True},
        )
        add_never_cache_headers(response)
        return response
