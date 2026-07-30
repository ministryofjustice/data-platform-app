from django.contrib.auth.decorators import login_not_required
from django.http import HttpResponse
from django.utils.decorators import method_decorator
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
