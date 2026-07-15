from django.urls import path

from ai_gateway.views import KeyCreateView, KeyListView, KeyRegenerateView

app_name = "ai_gateway"

urlpatterns = [
    path("keys/", KeyListView.as_view(), name="key_list"),
    path("keys/create/", KeyCreateView.as_view(), name="key_create"),
    path("keys/<str:key_name>/regenerate/", KeyRegenerateView.as_view(), name="key_regenerate"),
]
