from __future__ import annotations

from functools import cached_property
from typing import Any
from urllib.parse import urlencode

import sentry_sdk
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.cache import add_never_cache_headers
from django.views.generic import DeleteView, DetailView, FormView, ListView, TemplateView, View
from django.views.generic.detail import SingleObjectMixin

from ai_gateway.exceptions import AIGatewayError
from ai_gateway.filtering import VISIBLE_LIMIT, filter_models
from ai_gateway.forms import KeyCreateForm, KeyModelChangeForm, UsageMonthForm
from ai_gateway.models import Key, Team
from ai_gateway.services import KeyService, UsageService
from data_platform_app.mixins import FeatureRequiredMixin
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


class UsageView(FeatureRequiredMixin, ProjectScopedMixin, ProjectLayoutContextMixin, TemplateView):
    """
    The usage UI is a single page with GOV.UK tabs for Overview, Spend per API key and
    Spend per model.
    """

    template_name = "ai_gateway/usage.html"
    feature_flag = "AI_GATEWAY_COSTS"
    active_project_section = "ai_gateway"
    active_ai_gateway_section = "usage"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        try:
            ai_gateway_team = self.project.ai_gateway_team
        except Team.DoesNotExist:
            empty = {"has_usage": False}
            context.update({"overview_data": empty, "key_data": empty, "model_data": empty})
            return context

        try:
            context.update(self._get_usage_context(ai_gateway_team))
        except AIGatewayError as error:
            sentry_sdk.capture_exception(error)
            context["usage_error"] = True
            context["has_usage"] = False
            return context

        overview_data = context["overview_data"]
        if overview_data["has_usage"] and self.request.GET.get("daily") == "all":
            overview_data["daily_spend_preview"] = overview_data["daily_spend"]

        return context

    def _get_usage_context(self, team: Team) -> dict[str, Any]:
        with UsageService.from_settings(team=team) as service:
            month_choices = service.get_usage_month_choices()
            month_form = UsageMonthForm(
                self.request.GET or None,
                month_choices=month_choices,
            )

            selected_month = month_choices[0]
            if month_form.is_valid() and month_form.cleaned_data["month"]:
                selected_month = month_form.cleaned_data["month"]

            return {
                "month_form": month_form,
                "selected_month": selected_month,
                **service.get_usage(selected_month),
            }


class KeyListView(ProjectScopedMixin, ProjectLayoutContextMixin, ListView):
    template_name = "ai_gateway/key-list.html"
    context_object_name = "keys"
    active_project_section = "ai_gateway"
    active_ai_gateway_section = "keys"

    def get_queryset(self):
        return self.project.ai_gateway_keys.order_by("-created")


class AvailableModelsMixin:
    """Shared access to the models offered by the AI gateway."""

    project: Project

    @cached_property
    def available_models(self) -> list[dict[str, Any]]:
        with KeyService.from_settings() as service:
            return service.list_available_models(self.project)

    @cached_property
    def model_providers(self) -> list[str]:
        providers = {
            model.get("provider") for model in self.available_models if model.get("provider")
        }
        return sorted(providers)

    @cached_property
    def model_families(self) -> list[str]:
        families = {model.get("family") for model in self.available_models if model.get("family")}
        return sorted(families)

    @cached_property
    def available_models_by_name(self) -> dict[str, dict[str, Any]]:
        """
        Return a mapping of model_name to model dict for the available models for easier lookup.
        """
        return {model["model_name"]: model for model in self.available_models}

    def _model_display_names(self, model_ids: list[str]) -> list[str]:
        return [
            self.available_models_by_name[model_id]["display_name"]
            for model_id in model_ids
            if model_id in self.available_models_by_name
        ]


class ModelSelectionContextMixin(AvailableModelsMixin):
    """Builds shared context for model-selection tables with filtering and paging."""

    model_filter_url_name = "ai_gateway:key_create"

    def _model_filter_url(self, kwargs: dict[str, Any] | None = None) -> str:
        """Return the model-filter endpoint URL for the current view context."""
        return reverse(self.model_filter_url_name, kwargs=kwargs or dict(self.kwargs))

    def _selected_model_ids(self, params) -> list[str]:
        return params.getlist("models")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(self._model_list_context())
        return context

    def _valid_selected_model_ids(self, params) -> list[str]:
        return [
            model_id
            for model_id in self._selected_model_ids(params)
            if model_id in self.available_models_by_name
        ]

    def _pinned_models(
        self,
        selected_model_ids: list[str],
        matches: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Selected models excluded by the active filters, shown above the table in full."""
        matching_model_ids = {model["model_name"] for model in matches}

        return [
            self.available_models_by_name[model_id]
            for model_id in selected_model_ids
            if model_id not in matching_model_ids
        ]

    def _hidden_selected_models(
        self,
        selected_model_ids: list[str],
        visible_models: list[dict[str, Any]],
    ) -> list[str]:

        if not selected_model_ids:
            return []

        visible_model_ids = {model["model_name"] for model in visible_models}
        return [
            model["model_name"]
            for model in self.available_models
            if model["model_name"] in selected_model_ids
            and model["model_name"] not in visible_model_ids
        ]

    def _model_list_context(self) -> dict[str, Any]:
        """Build the filtered, paged model-selection context.

        Selected models are derived from request parameters and preserved across filtering and
        collapsing/expanding without session state.
        """
        params = self.request.POST if self.request.method == "POST" else self.request.GET
        search = params.get("search", "")
        provider = params.get("provider", "")
        family = params.get("family", "")
        expanded = params.get("expanded") == "1"
        selected_model_ids = self._valid_selected_model_ids(params)

        filtered_models = filter_models(
            self.available_models,
            search=search,
            provider=provider,
            family=family,
            selected_model_ids=selected_model_ids,
        )
        pinned_models = self._pinned_models(selected_model_ids, filtered_models)
        visible_matches = filtered_models if expanded else filtered_models[:VISIBLE_LIMIT]
        # Pinned models don't count toward the visible limit.
        visible_models = [*pinned_models, *visible_matches]
        hidden_selected_models = self._hidden_selected_models(selected_model_ids, visible_models)

        return {
            "model_filter_url_name": self.model_filter_url_name,
            "model_filter_url": self._model_filter_url(),
            "model_providers": self.model_providers,
            "model_families": self.model_families,
            "visible_models": visible_models,
            "hidden_selected_models": hidden_selected_models,
            "selected_models": selected_model_ids,
            "filter_search": search,
            "filter_provider": provider,
            "filter_family": family,
            "expanded": expanded,
            "match_count": len(filtered_models),
            "visible_count": len(visible_matches),
            "has_pinned_models": bool(pinned_models),
            "has_more": len(filtered_models) > len(visible_matches),
        }


class KeyCreateView(ProjectScopedMixin, ModelSelectionContextMixin, FormView):
    """Collects a key name and model selection, then hands off to the confirmation step."""

    template_name = "ai_gateway/key-create.html"
    form_class = KeyCreateForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["project"] = self.project
        kwargs["available_models"] = self.available_models
        if self.request.method == "GET" and self.request.GET.get("show_errors") == "1":
            kwargs["data"] = self.request.GET
        return kwargs

    def get_initial(self):
        initial = super().get_initial()
        initial["name"] = self.request.GET.get("name", "")
        return initial

    def get(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        if request.htmx:
            context = {"project": self.project, **self._model_list_context()}
            return render(request, "includes/ai_gateway/_model_list.html", context)
        return super().get(request, *args, **kwargs)

    def form_valid(self, form: KeyCreateForm) -> HttpResponse:
        query = urlencode(
            {"name": form.cleaned_data["name"], "models": form.cleaned_data["models"]},
            doseq=True,
        )
        url = reverse("ai_gateway:key_create_confirm", kwargs={"uuid": self.project.uuid})
        return redirect(f"{url}?{query}")


class KeyCreateConfirmView(ProjectScopedMixin, AvailableModelsMixin, View):
    """Reviews the submitted key details and creates the key on confirmation."""

    template_name = "ai_gateway/key-create-confirm.html"

    def _key_create_url(self, name: str, model_ids: list[str], show_errors: bool = False) -> str:
        params = {"name": name, "models": model_ids}
        if show_errors:
            params["show_errors"] = "1"
        query = urlencode(params, doseq=True)
        url = reverse("ai_gateway:key_create", kwargs={"uuid": self.project.uuid})
        return f"{url}?{query}"

    def _get_form(self, data) -> KeyCreateForm:
        return KeyCreateForm(
            data=data,
            project=self.project,
            available_models=self.available_models,
        )

    def get(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        form = self._get_form(request.GET)
        if not form.is_valid():
            return redirect(
                self._key_create_url(
                    name=request.GET.get("name", ""),
                    model_ids=request.GET.getlist("models"),
                    show_errors=True,
                )
            )

        name = form.cleaned_data["name"]
        model_ids = form.cleaned_data["models"]

        context = {
            "project": self.project,
            "key_name": name,
            "selected_model_ids": model_ids,
            "selected_model_names": self._model_display_names(model_ids),
            "change_url": self._key_create_url(name=name, model_ids=model_ids),
        }
        return render(request, self.template_name, context)

    def post(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        form = self._get_form(request.POST)
        if not form.is_valid():
            return redirect(
                self._key_create_url(
                    name=request.POST.get("name", ""),
                    model_ids=request.POST.getlist("models"),
                    show_errors=True,
                )
            )

        with KeyService.from_settings() as service:
            plaintext_key = service.create_key(
                project=self.project,
                name=form.cleaned_data["name"],
                models=form.cleaned_data["models"],
                created_by=request.user,
            )

        response = render(
            request,
            "ai_gateway/key-created.html",
            {"project": self.project, "plaintext_key": plaintext_key},
        )
        add_never_cache_headers(response)
        return response


class KeyScopedMixin(ProjectScopedMixin):
    """Resolves a key scoped to the current project."""

    @cached_property
    def key(self) -> Key:
        return get_object_or_404(self.project.ai_gateway_keys.all(), pk=self.kwargs["pk"])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if "key" not in context:
            context["key"] = self.key
        return context


class KeyModelChangeView(KeyScopedMixin, ModelSelectionContextMixin, FormView):
    """Lets users amend model selection for an existing key before review."""

    template_name = "ai_gateway/key-model-change.html"
    form_class = KeyModelChangeForm
    model_filter_url_name = "ai_gateway:key_model_change"

    def _htmx_model_list_context(self) -> dict[str, Any]:
        return {
            "project": self.project,
            "key": self.key,
            **self._model_list_context(),
        }

    @cached_property
    def current_key_model_ids(self) -> list[str]:
        with KeyService.from_settings() as service:
            models = service.get_models_for_key(self.key)

        if models == [KeyService.NO_DEFAULT_MODELS]:
            return []

        return [model for model in models if model in self.available_models_by_name]

    def _selected_model_ids(self, params) -> list[str]:
        selected_models = params.getlist("models")
        if selected_models:
            return selected_models
        return self.current_key_model_ids

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["available_models"] = self.available_models
        kwargs["current_models"] = self.current_key_model_ids
        if self.request.method == "GET" and self.request.GET.get("show_errors") == "1":
            kwargs["data"] = self.request.GET
        return kwargs

    def get(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        if request.htmx:
            return render(
                request,
                "includes/ai_gateway/_model_list.html",
                self._htmx_model_list_context(),
            )
        return super().get(request, *args, **kwargs)

    def form_valid(self, form: KeyModelChangeForm) -> HttpResponse:
        query = urlencode({"models": form.cleaned_data["models"]}, doseq=True)
        url = reverse(
            "ai_gateway:key_model_change_review",
            kwargs={"uuid": self.project.uuid, "pk": self.key.pk},
        )
        return redirect(f"{url}?{query}")


class KeyModelChangeConfirmView(KeyScopedMixin, AvailableModelsMixin, FormView):
    """Shows a review table of model changes before applying them."""

    template_name = "ai_gateway/key-model-change-review.html"
    form_class = KeyModelChangeForm

    def _ordered_model_ids(self, model_ids: set[str]) -> list[str]:
        return [
            model["model_name"]
            for model in self.available_models
            if model["model_name"] in model_ids
        ]

    def _ordered_model_names(self, model_ids: set[str]) -> list[str]:
        return self._model_display_names(self._ordered_model_ids(model_ids))

    def _change_url(self, model_ids: list[str] | None = None) -> str:
        url = reverse(
            "ai_gateway:key_model_change",
            kwargs={"uuid": self.project.uuid, "pk": self.key.pk},
        )
        if model_ids is None:
            return url
        return f"{url}?{urlencode({'models': model_ids}, doseq=True)}"

    @cached_property
    def current_gateway_models(self) -> list[str]:
        with KeyService.from_settings() as service:
            return service.get_models_for_key(self.key)

    @cached_property
    def current_models(self) -> set[str]:
        return {
            model for model in self.current_gateway_models if model != KeyService.NO_DEFAULT_MODELS
        }

    def form_valid(self, form: KeyModelChangeForm) -> HttpResponse:
        selected_model_ids = form.cleaned_data["models"]

        try:
            with KeyService.from_settings() as service:
                service.update_models_for_key(
                    key=self.key,
                    models=selected_model_ids,
                    changed_by=self.request.user,
                )
        except AIGatewayError as error:
            sentry_sdk.capture_exception(error)
            error_message = (
                'If this problem persists, you can <a class="govuk-link" '
                'href="https://moj.enterprise.slack.com/archives/C0B949G0J2X">raise an issue in '
                "the #ask-data-platform Slack channel</a>. Include your Project ID and Key ID ("
                "not your API key) in the message."
            )
            self.request.session["error_message"] = {
                "heading": "Could not update models",
                "message": error_message,
            }
            return redirect("ai_gateway:key_detail", uuid=self.project.uuid, pk=self.key.pk)

        self.request.session["success_message"] = {
            "heading": "Models changed",
            "message": "You've updated the models for this key",
        }
        return redirect("ai_gateway:key_detail", uuid=self.project.uuid, pk=self.key.pk)

    def form_invalid(self, form):
        params = {"models": form.data.getlist("models"), "show_errors": 1}
        querystring = urlencode(params, doseq=True)
        url = self._change_url()
        return redirect(f"{url}?{querystring}")

    def get(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        form = self.get_form()
        if not form.is_valid():
            return self.form_invalid(form=form)

        context = self.get_context_data(form=form)
        return self.render_to_response(context)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        form = kwargs["form"]
        selected_model_ids = form.cleaned_data["models"]
        selected_model_id_set = set(selected_model_ids)
        current_models = self.current_models

        added_model_ids = selected_model_id_set - current_models
        removed_model_ids = current_models - selected_model_id_set
        retained_model_ids = current_models & selected_model_id_set
        model_change_rows = [
            {
                "label": "Added",
                "models": self._ordered_model_names(added_model_ids),
            },
            {
                "label": "Removed",
                "models": self._ordered_model_names(removed_model_ids),
            },
            {
                "label": "Retained",
                "models": self._ordered_model_names(retained_model_ids),
            },
        ]

        context.update(
            {
                "change_url": self._change_url(selected_model_ids),
                "selected_model_ids": selected_model_ids,
                "model_change_rows": model_change_rows,
            }
        )
        return context

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()

        if self.request.method == "GET":
            kwargs["data"] = self.request.GET

        kwargs.update(
            available_models=self.available_models,
            current_models=self.current_models,
        )
        return kwargs


class KeyDetailView(KeyScopedMixin, DetailView):
    template_name = "ai_gateway/key-detail.html"
    context_object_name = "key"

    def get_queryset(self):
        return self.project.ai_gateway_keys.all()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["success_message"] = self.request.session.pop("success_message", None)
        context["error_message"] = self.request.session.pop("error_message", None)
        with KeyService.from_settings() as service:
            try:
                models = service.get_models_for_key(self.object)
                context["models"] = [
                    "None" if model == KeyService.NO_DEFAULT_MODELS else model for model in models
                ]
            except AIGatewayError as error:
                sentry_sdk.capture_exception(error)
                context["models"] = []
        return context


class KeyRegenerateView(ProjectScopedMixin, SingleObjectMixin, TemplateView):
    template_name = "ai_gateway/key-regenerate.html"
    context_object_name = "key"

    def get_queryset(self):
        return self.project.ai_gateway_keys.all()

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()

        try:
            with KeyService.from_settings() as service:
                plaintext_key = service.regenerate_key(key=self.object)
        except AIGatewayError as error:
            sentry_sdk.capture_exception(error)
            self.request.session["error_message"] = {
                "heading": "Could not regenerate key. Please try again later.",
            }
            return redirect("ai_gateway:key_detail", uuid=self.project.uuid, pk=self.object.pk)

        response = render(
            request,
            "ai_gateway/key-created.html",
            {"project": self.project, "plaintext_key": plaintext_key, "regenerated": True},
        )
        add_never_cache_headers(response)
        return response


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
