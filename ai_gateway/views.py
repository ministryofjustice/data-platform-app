from __future__ import annotations

from functools import cached_property

import sentry_sdk
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils.cache import add_never_cache_headers
from django.views.generic import DetailView, FormView, ListView, TemplateView

from ai_gateway.exceptions import AIGatewayError
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

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        with KeyService.from_settings() as service:
            try:
                context["models"] = service.get_models_for_key(self.object)
            except AIGatewayError as error:
                sentry_sdk.capture_exception(error)
                context["models"] = []
        return context


class KeyRegenerateView(ProjectScopedMixin, TemplateView):
    template_name = "ai_gateway/key-regenerate.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["project"] = self.project
        existing_key = self.project.ai_gateway_keys.get(pk=self.kwargs["pk"])
        context["key"] = existing_key
        return context

    def post(self, request, *args, **kwargs):
        key_id = kwargs["pk"]
        existing_key = self.project.ai_gateway_keys.get(pk=key_id)

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
