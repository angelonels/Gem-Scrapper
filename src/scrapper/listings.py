import json
from pathlib import Path
from urllib.parse import urljoin
from playwright.async_api import Page, Locator


BASE_URL = "https://bidplus.gem.gov.in"
CARD_SELECTOR = "div.card"


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

    item_locator = card.locator('[data-content]')

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
    }
async def extract_listing_data(page: Page) -> list[dict]:
    await page.wait_for_selector(CARD_SELECTOR, state="attached", timeout=30_000)

    cards = page.locator(CARD_SELECTOR)
    total_cards = await cards.count()

    results = []

    for index in range(total_cards):
        card = cards.nth(index)
        data = await extract_one_card(card)

        if data["bid_ra_number"]:
            results.append(data)

    return results


def save_raw_json(data: list[dict], filename: str = "listings_data.json") -> Path:
    output_dir = Path("data/raw")
    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = output_dir / filename

    with output_path.open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=2, ensure_ascii=False)

    return output_path