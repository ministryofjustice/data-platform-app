from __future__ import annotations

from functools import cached_property
from typing import Any

import sentry_sdk
from django.conf import settings
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.utils.cache import add_never_cache_headers
from django.views.generic import DeleteView, DetailView, FormView, ListView

from ai_gateway.exceptions import AIGatewayError
from ai_gateway.forms import KeyCreateForm, KeyModelFilterForm
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
    def available_models(self) -> list[dict[str, Any]]:
        with KeyService.from_settings() as service:
            models = service.list_selectable_models_for_key()

        if settings.DEBUG:
            return models + self._debug_extra_models()

        return models

    @cached_property
    def model_providers(self) -> list[str]:
        providers = {
            model.get("litellm_params", {}).get("ai_model_provider")
            for model in self.available_models
            if model.get("litellm_params", {}).get("ai_model_provider")
        }
        return sorted(providers)

    @cached_property
    def model_filter_form(self) -> KeyModelFilterForm:
        return KeyModelFilterForm(
            self.request.GET or None,
            provider_choices=self.model_providers,
        )

    @cached_property
    def filtered_available_models(self) -> list[dict[str, Any]]:
        return self.model_filter_form.filter_models(self.available_models)

    @staticmethod
    def _debug_extra_models() -> list[dict[str, Any]]:
        """Return extra local models so browser filtering can be tested quickly."""
        return [
            {
                "model_name": "debug-openai-gpt-4-1-mini",
                "litellm_params": {
                    "ai_model_name": "OpenAI GPT-4.1 Mini",
                    "ai_model_provider": "OpenAI",
                },
            },
            {
                "model_name": "debug-gemini-2-5-pro",
                "litellm_params": {
                    "ai_model_name": "Gemini 2.5 Pro",
                    "ai_model_provider": "Google",
                },
            },
            {
                "model_name": "debug-mistral-large-2",
                "litellm_params": {
                    "ai_model_name": "Mistral Large 2",
                    "ai_model_provider": "Mistral",
                },
            },
            {
                "model_name": "debug-llama-3-3-70b",
                "litellm_params": {
                    "ai_model_name": "Llama 3.3 70B",
                    "ai_model_provider": "Meta",
                },
            },
            {
                "model_name": "debug-bedrock-nova-pro",
                "litellm_params": {
                    "ai_model_name": "Amazon Nova Pro",
                    "ai_model_provider": "Amazon Bedrock",
                },
            },
        ]

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["project"] = self.project
        kwargs["available_models"] = self.filtered_available_models
        return kwargs

    def get_initial(self):
        initial = super().get_initial()
        key_name = self.request.GET.get("name", "").strip()
        if key_name:
            initial["name"] = key_name
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["project"] = self.project
        context["available_models"] = self.filtered_available_models
        context["model_filter_form"] = self.model_filter_form
        return context

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


class KeyRevokeView(ProjectScopedMixin, DeleteView):
    template_name = "ai_gateway/key-revoke.html"
    context_object_name = "key"
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        return self.project.ai_gateway_keys.all()

    def get_success_url(self):
        return self.project.get_absolute_keys_url()

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        with KeyService.from_settings() as service:
            service.delete_key(self.object)
        self.request.session["success_message"] = {
            "heading": "Key revoked",
            "message": f"You've revoked {self.object.name}",
        }
        return HttpResponseRedirect(self.get_success_url())
