from django.conf import settings


def feature_enabled(feature_name: str) -> bool:
    """
    Check if a feature is enabled based on the FEATURE_FLAGS dictionary.

    Args:
        feature_name (str): The name of the feature to check.
    Returns:
        bool: True if the feature is enabled, False otherwise.
    """

    return settings.FEATURE_FLAGS.get(feature_name, False)
