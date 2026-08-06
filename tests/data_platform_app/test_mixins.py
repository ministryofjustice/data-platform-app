import pytest
from django.core.exceptions import ImproperlyConfigured
from django.http import Http404, HttpResponse

from data_platform_app.mixins import FeatureRequiredMixin


class StubView:
    def dispatch(self, request, *args, **kwargs):
        return HttpResponse("view called")


class FlaggedStubView(FeatureRequiredMixin, StubView):
    feature_flag = "EXAMPLE_FEATURE"


class TestFeatureRequiredMixin:
    def test_dispatches_when_feature_is_enabled(self, settings, rf):
        settings.FEATURE_FLAGS = {"EXAMPLE_FEATURE": True}
        response = FlaggedStubView().dispatch(rf.get("/"))

        assert response.status_code == 200
        assert response.content == b"view called"

    def test_raises_404_when_feature_is_disabled(self, settings, rf):
        settings.FEATURE_FLAGS = {"EXAMPLE_FEATURE": False}
        with pytest.raises(Http404):
            FlaggedStubView().dispatch(rf.get("/"))

    def test_incorrectly_configured_when_feature_flag_not_set(self, rf):
        class NoFeatureFlagView(FeatureRequiredMixin, StubView):
            pass

        with pytest.raises(ImproperlyConfigured) as exc_info:
            NoFeatureFlagView().dispatch(rf.get("/"))

        assert "feature_flag attribute must be set on the view." in str(exc_info.value)
