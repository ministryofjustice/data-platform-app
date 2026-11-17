import hmac

import sentry_sdk
from azure_auth.views import azure_auth_callback
from django.conf import settings
from django.contrib.auth import get_user_model, login
from django.contrib.auth.decorators import login_not_required
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.views.generic import TemplateView


@login_not_required
def auth_callback(request: HttpRequest) -> HttpResponse:
    """Offer a fresh sign-in when MSAL rejects an outdated authentication flow."""
    try:
        return azure_auth_callback(request)
    except ValueError as exc:
        if not str(exc).startswith("state mismatch:"):
            raise

        sentry_sdk.capture_message("auth_state_mismatch", level="warning")
        return render(
            request,
            "auth_sign_in_again.html",
            context={"google_analytics_id": ""},
            status=400,
        )


class ProductPageMixin:
    show_masthead = True
    inverse_header = True

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["show_masthead"] = self.show_masthead
        context["inverse_header"] = self.inverse_header
        return context


@method_decorator(login_not_required, name="dispatch")
class HomeView(ProductPageMixin, TemplateView):
    template_name = "home.html"


@method_decorator(login_not_required, name="dispatch")
class RoadmapView(ProductPageMixin, TemplateView):
    template_name = "roadmap.html"
    show_masthead = False


@method_decorator(login_not_required, name="dispatch")
class DataFactoriesView(ProductPageMixin, TemplateView):
    template_name = "data_factories.html"
    show_masthead = False


@method_decorator(login_not_required, name="dispatch")
class AccessibilityStatementView(ProductPageMixin, TemplateView):
    template_name = "accessibility_statement.html"
    show_masthead = False


class LandingView(TemplateView):
    template_name = "landing.html"


@login_not_required
def healthcheck(request):
    """
    Healthcheck view for the app.
    """
    return HttpResponse("OK")


@csrf_exempt
@require_POST
@login_not_required
def e2e_login(request: HttpRequest) -> HttpResponse:
    provided_token = request.headers.get("X-E2E-Token", "").encode()
    configured_token = settings.E2E_AUTH_TOKEN.encode()
    if not hmac.compare_digest(provided_token, configured_token):
        return HttpResponse(status=403)

    user_model = get_user_model()
    try:
        user = user_model.objects.get(email__iexact=settings.E2E_USER_EMAIL)
    except user_model.DoesNotExist, user_model.MultipleObjectsReturned:
        return HttpResponse(status=403)

    if not user.is_active:
        return HttpResponse(status=403)

    login(request, user, backend=settings.AUTHENTICATION_BACKENDS[0])
    return JsonResponse({"authenticated": True})
