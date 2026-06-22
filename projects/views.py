from django.views.generic.base import TemplateView


# Create your views here.
class ListView(TemplateView):
    template_name = "projects/list.html"
