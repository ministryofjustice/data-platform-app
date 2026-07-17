import os


def get_azure_redirect_uri(app_env) -> str:
    uri = os.environ.get("AZURE_REDIRECT_URI")

    if uri:
        return uri

    protocol = "https://"
    base_url = "data-platform.service.justice.gov.uk/sso/callback/"

    if app_env.lower() == "production":
        return f"{protocol}{base_url}"
    else:
        return f"{protocol}{app_env.lower()}.{base_url}"
