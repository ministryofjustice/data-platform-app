import hmac

from django.conf import settings
from django.contrib.auth import get_user_model, login
from django.contrib.auth.decorators import login_not_required
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.views.generic import TemplateView


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
