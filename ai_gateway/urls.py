from django.urls import path

from ai_gateway.views import KeyCreateView, KeyDetailView, KeyListView

app_name = "ai_gateway"

urlpatterns = [
    path("keys/", KeyListView.as_view(), name="key_list"),
    path("keys/create/", KeyCreateView.as_view(), name="key_create"),
    path("keys/<int:pk>/", KeyDetailView.as_view(), name="key_detail"),
]
