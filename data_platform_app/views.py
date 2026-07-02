from django.contrib.auth.decorators import login_not_required
from django.http import HttpResponse
from django.utils.decorators import method_decorator
from django.views.generic import TemplateView


@method_decorator(login_not_required, name="dispatch")
class HomeView(TemplateView):
    template_name = "home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["show_masthead"] = True
        return context


@method_decorator(login_not_required, name="dispatch")
class RoadmapView(TemplateView):
    template_name = "roadmap.html"


@method_decorator(login_not_required, name="dispatch")
class DataFactoriesView(TemplateView):
    template_name = "data_factories.html"


class LandingView(TemplateView):
    template_name = "landing.html"


@login_not_required
def healthcheck(request):
    """
    Healthcheck view for the app.
    """
    return HttpResponse("OK")
