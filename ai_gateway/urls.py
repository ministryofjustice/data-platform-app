from django.urls import path

from ai_gateway.views import (
    KeyCreateView,
    KeyDetailView,
    KeyListView,
    KeyRegenerateView,
    KeyRevokeView,
)

app_name = "ai_gateway"

urlpatterns = [
    path("keys/", KeyListView.as_view(), name="key_list"),
    path("keys/create/", KeyCreateView.as_view(), name="key_create"),
    path("keys/<int:pk>/", KeyDetailView.as_view(), name="key_detail"),
    path("keys/<int:pk>/regenerate/", KeyRegenerateView.as_view(), name="key_regenerate"),
    path("keys/<int:pk>/revoke/", KeyRevokeView.as_view(), name="key_revoke"),
]
