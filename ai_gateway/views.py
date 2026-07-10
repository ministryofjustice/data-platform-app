from __future__ import annotations

from functools import cached_property

from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.generic import FormView, ListView, TemplateView

from ai_gateway.forms import KeyCreateForm
from ai_gateway.services import KeyService
from projects.mixins import ProjectLayoutContextMixin
from projects.models import Project

SESSION_PLAINTEXT_KEY = "ai_gateway_plaintext_key"


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
    """Generates a virtual key for a project and shows it once."""

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

        self.request.session[SESSION_PLAINTEXT_KEY] = plaintext_key
        return redirect("ai_gateway:key_created", uuid=self.project.uuid)


@method_decorator(never_cache, name="dispatch")
class KeyCreatedView(ProjectScopedMixin, TemplateView):
    """Displays a newly created key once."""

    template_name = "ai_gateway/key-created.html"

    def get(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        plaintext_key = request.session.pop(SESSION_PLAINTEXT_KEY, None)
        if not plaintext_key:
            return redirect("ai_gateway:key_list", uuid=self.project.uuid)

        context = self.get_context_data(**kwargs)
        context["plaintext_key"] = plaintext_key
        return self.render_to_response(context)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["project"] = self.project
        return context
