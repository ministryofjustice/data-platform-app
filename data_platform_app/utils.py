import os


def build_base_url(app_env: str) -> str:
    """Return the base URL for the app environment."""
    app_env = app_env.strip().casefold()
    if app_env == "local":
        return "http://localhost:8000"

    domain = "data-platform.service.justice.gov.uk"
    if app_env == "production":
        return f"https://{domain}"

    return f"https://{app_env}.{domain}"


def get_azure_redirect_uri(app_env: str) -> str:
    uri = os.environ.get("AZURE_REDIRECT_URI")

    if uri:
        return uri

    base_url = build_base_url(app_env)
    return f"{base_url}/sso/callback/"
