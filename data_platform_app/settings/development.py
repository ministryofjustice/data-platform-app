from .production import *  # noqa: F401, F403

DEBUG = False

ALLOWED_HOSTS += [  # noqa: F405
    "development.data-platform.service.justice.gov.uk",
    "preproduction.data-platform.service.justice.gov.uk",
    "test.data-platform.service.justice.gov.uk",
    ".elb.amazonaws.com",
]

FEATURE_FLAGS = {
    **FEATURE_FLAGS,  # noqa: F405
    "AI_GATEWAY_COSTS": True,
}
