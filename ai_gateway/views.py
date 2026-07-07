from __future__ import annotations

from functools import cached_property

from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.views.generic import FormView, ListView

from ai_gateway.forms import KeyCreateForm
from ai_gateway.services import KeyService
from projects.models import Project


class ProjectScopedMixin:
    """Resolves the project from the URL, limited to the requesting user's projects."""

    request: HttpRequest
    kwargs: dict

    @cached_property
    def project(self) -> Project:
        return get_object_or_404(
            Project.objects.filter(user_permissions__user=self.request.user).distinct(),
            slug=self.kwargs["slug"],
        )


class KeyListView(ProjectScopedMixin, ListView):
    template_name = "ai_gateway/key-list.html"
    context_object_name = "keys"

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

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["project"] = self.project
        return context

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["project"] = self.project
        return kwargs

    def form_valid(self, form: KeyCreateForm) -> HttpResponse:
        with KeyService.from_settings() as service:
            plaintext_key = service.create_key(
                self.project, form.cleaned_data["name"], self.request.user
            )

        return render(
            self.request,
            "ai_gateway/key-created.html",
            {"project": self.project, "plaintext_key": plaintext_key},
        )
