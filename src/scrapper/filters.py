from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError


CARD_SELECTOR = "div.card"
BID_RA_CHECKBOX = "#bidrastatus"
AWARDED_CHECKBOX = "#bid_awarded"


async def is_site_loaded(page: Page) -> bool:

    try:
        await page.wait_for_selector(CARD_SELECTOR, state="attached", timeout=30_000)
        await page.wait_for_selector(BID_RA_CHECKBOX, state="attached", timeout=30_000)
        await page.wait_for_selector(AWARDED_CHECKBOX, state="attached", timeout=30_000)
        return True

    except PlaywrightTimeoutError:
        return False


async def is_checkbox_selected(page: Page, checkbox_selector: str) -> bool:

    checkbox = page.locator(checkbox_selector)

    await checkbox.wait_for(state="attached", timeout=30_000)

    return await checkbox.is_checked()


async def check_checkbox_if_needed(page: Page, checkbox_selector: str) -> None:


    already_selected = await is_checkbox_selected(page, checkbox_selector)

    if already_selected:

        return

    print(f"Checking checkbox: {checkbox_selector}")

    await page.locator(checkbox_selector).check()

    await page.wait_for_load_state("domcontentloaded")
    await page.wait_for_load_state("networkidle")


async def apply_filters(page: Page) -> None:

    if not await is_site_loaded(page):
        raise RuntimeError("Site not loaded before applying Bid/RA filter")

    await check_checkbox_if_needed(page, BID_RA_CHECKBOX)

    if not await is_site_loaded(page):
        raise RuntimeError("Site not loaded after applying Bid/RA filter")

    await check_checkbox_if_needed(page, AWARDED_CHECKBOX)

    if not await is_site_loaded(page):
        raise RuntimeError("Site not loaded after applying Awarded filter")

    print("filters applied successfully")