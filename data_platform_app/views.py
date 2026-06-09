from django.views.generic import TemplateView


class HomeView(TemplateView):
    template_name = "home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["show_masthead"] = True
        return context


class RoadmapView(TemplateView):
    template_name = "roadmap.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["show_masthead"] = False
        return context


class DataFactoriesView(TemplateView):
    template_name = "data_factories.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["show_masthead"] = False
        return context
