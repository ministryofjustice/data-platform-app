from data_platform_app.utils import get_azure_redirect_uri


class TestGetAzureRedirectUri:
    """Tests for get_azure_redirect_uri function."""

    def test_returns_environment_variable_when_set(self, monkeypatch):
        """When AZURE_REDIRECT_URI env var is set, return its value."""
        custom_uri = "https://custom.example.com/callback/"
        monkeypatch.setenv("AZURE_REDIRECT_URI", custom_uri)

        result = get_azure_redirect_uri("development")

        assert result == custom_uri

    def test_returns_environment_variable_regardless_of_app_env(self, monkeypatch):
        """When AZURE_REDIRECT_URI env var is set, return its value regardless of app_env."""
        custom_uri = "https://custom.example.com/callback/"
        monkeypatch.setenv("AZURE_REDIRECT_URI", custom_uri)

        result = get_azure_redirect_uri("production")

        assert result == custom_uri

    def test_production_uri_without_env_var(self, monkeypatch):
        """When app_env is production and env var not set, return production URI."""
        monkeypatch.delenv("AZURE_REDIRECT_URI", raising=False)

        result = get_azure_redirect_uri("production")

        assert result == "https://data-platform.service.justice.gov.uk/sso/callback/"

    def test_preproduction_uri_without_env_var(self, monkeypatch):
        """When app_env is preproduction and env var not set, return preproduction URI."""
        monkeypatch.delenv("AZURE_REDIRECT_URI", raising=False)

        result = get_azure_redirect_uri("preproduction")

        assert result == "https://preproduction.data-platform.service.justice.gov.uk/sso/callback/"

    def test_development_uri_without_env_var(self, monkeypatch):
        """When app_env is development and env var not set, return development URI."""
        monkeypatch.delenv("AZURE_REDIRECT_URI", raising=False)

        result = get_azure_redirect_uri("development")

        assert result == "https://development.data-platform.service.justice.gov.uk/sso/callback/"

    def test_custom_env_uri_without_env_var(self, monkeypatch):
        """When app_env is custom and env var not set, return custom env URI."""
        monkeypatch.delenv("AZURE_REDIRECT_URI", raising=False)

        result = get_azure_redirect_uri("custom-env")

        assert result == "https://custom-env.data-platform.service.justice.gov.uk/sso/callback/"
