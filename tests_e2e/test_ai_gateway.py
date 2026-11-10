from uuid import uuid4

from playwright.sync_api import Page, expect


def _summary_value(page: Page, label: str) -> str:
    value = (
        page.locator(".govuk-summary-list__row")
        .filter(has=page.locator("dt", has_text=label))
        .locator("dd")
    )
    expect(value).to_be_visible()
    return value.inner_text().strip()


def _first_model_id(page: Page) -> str:
    value = page.locator("#model-1")
    expect(value).to_be_visible()
    return value.inner_text().strip()


def test_creates_api_key(authenticated_page, e2e_base_url: str, project_uuid: str) -> None:
    """
    Test the creation of an API key in the AI Gateway.
    Verifies that the key is created successfully and can be revoked.
    Requires an existing project.
    """
    page = authenticated_page
    key_name = f"e2e-{uuid4().hex[:12]}"
    key_list_url = f"{e2e_base_url}/app/projects/{project_uuid}/ai-gateway/keys/"

    try:
        page.goto(key_list_url)
        expect(page.get_by_role("heading", name="API keys")).to_be_visible()
        page.get_by_role("link", name="Create API key").click()

        # check a new key can be created and there are models to select
        expect(page.get_by_role("heading", name="Create a key")).to_be_visible()
        model_table = page.locator(".govuk-table.moj-multi-select")
        expect(model_table).to_be_visible()
        expect(model_table).not_to_contain_text("No results found.")

        # select the first available model and fill in the key name
        first_model_row = model_table.get_by_role("row").nth(1)
        model_name = first_model_row.locator("td").nth(1).inner_text()
        first_model_row.get_by_role("checkbox").check()
        page.get_by_role("textbox", name="Key name").fill(key_name)

        # check review page is displayed with correct details
        page.get_by_role("button", name="Continue").click()
        expect(page.get_by_role("heading", name="Review details")).to_be_visible()
        expect(page.locator("body")).to_contain_text(key_name)
        expect(page.locator("body")).to_contain_text(model_name)
        page.get_by_role("button", name="Create key").click()

        # check the key details are displayed correctly
        expect(page.get_by_role("heading", name="Store your API key")).to_be_visible()
        expect(page.locator("body")).to_contain_text("created an API key for")
        expect(page.locator("#plaintext-key")).not_to_be_empty()
    finally:
        # cleanup the created key if it exists
        page.goto(key_list_url)
        created_key = page.get_by_role("row").filter(has_text=key_name)
        if created_key.count():
            created_key.get_by_role("link", name="Manage").click()
            page.get_by_role("link", name="Revoke", exact=True).click()
            page.get_by_role("button", name="Revoke", exact=True).click()
            expect(page.locator("body")).to_contain_text(f"You've revoked {key_name}")


def test_update_models_for_existing_key(
    authenticated_page, e2e_base_url: str, project_uuid: str
) -> None:
    """
    Test updating the models for an existing API key in the AI Gateway.
    Verifies that the models can be changed successfully.
    Requires an existing project and at least one API key.
    """
    page = authenticated_page
    key_list_url = f"{e2e_base_url}/app/projects/{project_uuid}/ai-gateway/keys/"

    # find the existing key
    page.goto(key_list_url)
    expect(page.get_by_role("heading", name="API keys")).to_be_visible()
    first_key_row = page.get_by_role("row").nth(1)
    first_key_row.get_by_role("link", name="Manage").click()

    # store key details to assert against later
    key_id = _summary_value(page, "Key ID")
    old_model_id = _first_model_id(page)
    page.get_by_role("link", name="Change models").click()
    expect(page.get_by_role("heading", name="Change models")).to_be_visible()

    # ensure there are models available to select
    model_table = page.locator(".govuk-table.moj-multi-select")
    expect(model_table).to_be_visible()
    expect(model_table).not_to_contain_text("No results found.")

    # select a different model than the one currently assigned
    first_model_row = model_table.get_by_role("row").nth(1)
    first_model_row.get_by_role("checkbox").uncheck()
    second_model_row = model_table.get_by_role("row").nth(2)
    second_model_row.get_by_role("checkbox").check()
    page.get_by_role("button", name="Review changes").click()
    expect(page.get_by_role("heading", name="Review model changes")).to_be_visible()

    # save the changes and check that the models have been updated successfully
    page.get_by_role("button", name="Save changes").click()
    expect(page.get_by_role("heading", name="Models changed")).to_be_visible()
    expect(page.locator("body")).to_contain_text("You've updated the models for this key")
    expect(page.locator("body")).to_contain_text(key_id)
    new_model_id = _first_model_id(page)
    assert new_model_id != old_model_id


def test_regenerate_existing_key(authenticated_page, e2e_base_url: str, project_uuid: str) -> None:
    """
    Test regenerating an existing API key in the AI Gateway.
    Verifies that the key can be regenerated successfully, and this changes the key details.
    Requires an existing project and at least one API key.
    """
    page = authenticated_page
    key_list_url = f"{e2e_base_url}/app/projects/{project_uuid}/ai-gateway/keys/"

    # find the existing key
    page.goto(key_list_url)
    expect(page.get_by_role("heading", name="API keys")).to_be_visible()
    first_key_row = page.get_by_role("row").nth(1)
    first_key_row.get_by_role("link", name="Manage").click()

    # store key details to assert against later
    key_id = _summary_value(page, "Key ID")
    masked_key = _summary_value(page, "API key")
    model_id = _first_model_id(page)
    page.get_by_role("link", name="Regenerate").click()
    expect(page.get_by_role("heading", name="Regenerate key")).to_be_visible()
    expect(
        page.get_by_role("heading", name="Are you sure you want to regenerate this API key?")
    ).to_be_visible()

    # confirm regeneration and check that the new key is displayed
    page.get_by_role("button", name="Regenerate").click()
    expect(page.get_by_role("heading", name="Store your API key")).to_be_visible()
    expect(page.locator("body")).to_contain_text("You've regenerated an API key")
    expect(page.locator("#plaintext-key")).not_to_be_empty()

    # assert that the key details have been updated correctly
    page.get_by_role("link", name="Done").click()
    expect(page.locator("body")).not_to_contain_text(key_id)
    expect(page.locator("body")).not_to_contain_text(masked_key)
    new_key_id = _summary_value(page, "Key ID")
    new_masked_key = _summary_value(page, "API key")
    assert new_key_id != key_id
    assert new_masked_key != masked_key
    new_model_id = _first_model_id(page)
    assert new_model_id == model_id
