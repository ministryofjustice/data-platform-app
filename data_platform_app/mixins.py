from django.core.exceptions import ImproperlyConfigured
from django.http import Http404

from .feature_flags import feature_enabled


class FeatureRequiredMixin:
    """
    Mixin to check if a feature is enabled based on the FEATURE_FLAGS setting. Views using this
    mixin must define a `feature_flag` attribute.
    Raises 404 if not enabled, otherwise proceeds as normal.

    Example usage:
        class MyView(FeatureRequiredMixin, View):
            feature_flag = "MY_FEATURE"
    """

    feature_flag: str | None = None

    def dispatch(self, request, *args, **kwargs):
        if not self.feature_flag:
            raise ImproperlyConfigured("feature_flag attribute must be set on the view.")

        if not feature_enabled(self.feature_flag):
            raise Http404()

        return super().dispatch(request, *args, **kwargs)
