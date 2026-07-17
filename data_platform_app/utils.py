import os


def get_azure_redirect_uri() -> str:
    uri = os.environ.get("AZURE_REDIRECT_URI")

    if uri:
        return uri

    protocol = "https://"
    base_url = "data-platform.service.justice.gov.uk/sso/callback/"
    environment = os.environ.get("APP_ENV", "development")

    if environment == "production":
        return f"{protocol}{base_url}"
    else:
        return f"{protocol}{environment}.{base_url}"
