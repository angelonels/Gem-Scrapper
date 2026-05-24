import json
from pathlib import Path
from urllib.parse import urljoin

from playwright.async_api import Page, Locator, TimeoutError as PlaywrightTimeoutError


BASE_URL = "https://bidplus.gem.gov.in"
CARD_SELECTOR = "div.card"
NEXT_BUTTON_SELECTOR = "a.page-link.next"


async def get_text(card: Locator, selector: str) -> str | None:
    locator = card.locator(selector)

    if await locator.count() == 0:
        return None

    text = await locator.first.inner_text()
    text = " ".join(text.split())

    return text or None


async def extract_one_card(card: Locator) -> dict:
    bid_no = await get_text(card, ".bid_no_hover")

    quantity_text = await get_text(
        card,
        ".col-md-4 .row:nth-child(2)"
    )

    department_text = await get_text(
        card,
        ".col-md-5 .row:nth-child(2)"
    )

    end_date = await get_text(card, ".end_date")

    bid_link = None
    bid_link_locator = card.locator(".bid_no_hover")

    if await bid_link_locator.count() > 0:
        href = await bid_link_locator.first.get_attribute("href")

        if href:
            bid_link = urljoin(BASE_URL, href)

    bid_result_link = None
    bid_result_link_locator = card.locator('a:has(input[value="View BID Results"])')

    if await bid_result_link_locator.count() > 0:
        href = await bid_result_link_locator.first.get_attribute("href")

        if href:
            bid_result_link = urljoin(BASE_URL, href)

    item_locator = card.locator("[data-content]")

    item_category = None

    if await item_locator.count() > 0:
        item_category = await item_locator.first.get_attribute("data-content")

    if item_category:
        item_category = " ".join(item_category.split())

    quantity = None

    if quantity_text:
        quantity = quantity_text.replace("Quantity:", "").strip()

    return {
        "bid_ra_number": bid_no,
        "item_category": item_category,
        "buyer_department": department_text,
        "quantity": quantity,
        "bid_value": None,
        "award_date": end_date,
        "bid_link": bid_link,
        "bid_result_link": bid_result_link,
    }


async def go_to_next_page(page: Page) -> bool:
    next_button = page.locator(NEXT_BUTTON_SELECTOR).first

    if await next_button.count() == 0:
        print("Next button not found.")
        return False

    if not await next_button.is_visible():
        print("Next button is not visible.")
        return False

    first_bid_before = None
    first_card = page.locator(CARD_SELECTOR).first

    if await first_card.count() > 0:
        first_bid_before = await get_text(first_card, ".bid_no_hover")

    print("Moving to next page...")

    await next_button.click()

    try:
        await page.wait_for_function(
            """
            (oldBid) => {
                const firstBid = document.querySelector("div.card .bid_no_hover");

                if (!firstBid) {
                    return false;
                }

                const currentBid = firstBid.textContent.trim();

                if (!oldBid) {
                    return currentBid.length > 0;
                }

                return currentBid !== oldBid;
            }
            """,
            arg=first_bid_before,
            timeout=20_000,
        )

    except PlaywrightTimeoutError:
        print("Page did not change after clicking Next.")
        return False

    await page.wait_for_selector(CARD_SELECTOR, state="attached", timeout=30_000)

    return True


async def extract_listing_data(page: Page, total_pages: int = 10) -> list[dict]:
    results = []
    seen_bid_numbers = set()

    for page_number in range(1, total_pages + 1):
        print(f"Extracting page {page_number}...")

        await page.wait_for_selector(CARD_SELECTOR, state="attached", timeout=30_000)

        cards = page.locator(CARD_SELECTOR)
        total_cards = await cards.count()

        print(f"Found {total_cards} cards on page {page_number}")

        for index in range(total_cards):
            card = cards.nth(index)
            data = await extract_one_card(card)

            bid_number = data.get("bid_ra_number")

            if not bid_number:
                continue

            if bid_number in seen_bid_numbers:
                continue

            seen_bid_numbers.add(bid_number)
            results.append(data)

        if page_number == total_pages:
            break

        moved = await go_to_next_page(page)

        if not moved:
            print("Could not move to next page. Stopping pagination.")
            break

    return results


def save_raw_json(data: list[dict], filename: str = "listings_data.json") -> Path:
    output_dir = Path("data/raw")
    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = output_dir / filename

    with output_path.open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=2, ensure_ascii=False)

    return output_path
