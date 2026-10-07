from playwright.sync_api import expect


def test_product_pages(page, live_server):
    page.goto(live_server.url)
    expect(page).to_have_title("Justice Data Platform | Ministry of Justice")

    page.get_by_role("link", name="Roadmap", exact=True).click()
    expect(page).to_have_title("Roadmap | Justice Data Platform | Ministry of Justice")

    page.get_by_role("link", name="Data factories", exact=True).click()

    expect(page).to_have_title("Data factories | Justice Data Platform | Ministry of Justice")
