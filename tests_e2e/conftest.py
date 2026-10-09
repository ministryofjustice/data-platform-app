import os

import pytest


@pytest.fixture(scope="session")
def e2e_base_url() -> str:
    return os.environ["E2E_BASE_URL"].rstrip("/")


@pytest.fixture(scope="session")
def project_uuid() -> str:
    return os.environ["E2E_PROJECT_UUID"]


@pytest.fixture
def authenticated_page(page, e2e_base_url: str):
    page.set_default_timeout(5_000)
    page.set_default_navigation_timeout(10_000)

    response = page.context.request.post(
        f"{e2e_base_url}/__e2e__/login/",
        headers={"X-E2E-Token": os.environ["E2E_AUTH_TOKEN"]},
        timeout=10_000,
    )
    assert response.ok, f"E2E login failed with HTTP {response.status}."
    return page
