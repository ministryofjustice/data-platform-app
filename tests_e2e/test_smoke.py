from playwright.sync_api import expect


def test_product_pages(page, e2e_base_url: str) -> None:
    page.goto(e2e_base_url)
    expect(page).to_have_title("Justice Data Platform | Ministry of Justice")

    page.get_by_role("link", name="Roadmap", exact=True).click()
    expect(page.get_by_role("heading", name="Roadmap", level=1)).to_be_visible()

    page.get_by_role("link", name="Data factories", exact=True).click()
    expect(page.get_by_role("heading", name="Data factories", level=1)).to_be_visible()
