"""
URL configuration for data_platform_app project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from azure_auth.views import azure_auth_callback, azure_auth_login, azure_auth_logout
from django.conf import settings
from django.contrib import admin
from django.contrib.auth.decorators import login_not_required
from django.urls import path
from django.urls.conf import include

from data_platform_app.views import (
    DataFactoriesView,
    HomeView,
    LandingView,
    RoadmapView,
    healthcheck,
)

urlpatterns = [
    path("projects/", include("projects.urls")),
    path("", HomeView.as_view(), name="home"),
    path("roadmap/", RoadmapView.as_view(), name="roadmap"),
    path("data-factories/", DataFactoriesView.as_view(), name="data_factories"),
    path("landing/", LandingView.as_view(), name="landing"),
    path("admin/", admin.site.urls),
    path("healthcheck/", healthcheck, name="healthcheck"),
    path("login/", login_not_required(azure_auth_login), name="login"),
    path("logout/", login_not_required(azure_auth_logout), name="logout"),
    path("sso/callback/", login_not_required(azure_auth_callback), name="auth_callback"),
]

if settings.DEBUG and "debug_toolbar" in settings.INSTALLED_APPS:
    # Third-party
    from debug_toolbar.toolbar import debug_toolbar_urls  # noqa

    urlpatterns += debug_toolbar_urls()
