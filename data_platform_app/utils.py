import os


def get_azure_redirect_uri(app_env: str) -> str:
    uri = os.environ.get("AZURE_REDIRECT_URI")

    if uri:
        return uri

    env = app_env.strip().casefold()
    base_url = "data-platform.service.justice.gov.uk/sso/callback/"

    if env == "production":
        return f"https://{base_url}"

    return f"https://{env}.{base_url}"
