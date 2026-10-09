from django.urls import path

from data_platform_app.urls import urlpatterns as app_urlpatterns
from data_platform_app.views import e2e_login

urlpatterns = [*app_urlpatterns, path("__e2e__/login/", e2e_login)]
