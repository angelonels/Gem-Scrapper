import asyncio
from playwright.async_api import async_playwright
from filters import apply_filters
from listings import extract_listing_data, save_raw_json
URL = "https://bidplus.gem.gov.in/all-bids"

async def main() -> None:
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,

        )
        context = await browser.new_context(
            ignore_https_errors=True,
        )
        page = await context.new_page()

        print(f"Opening website: {URL}")

        await page.goto(
            URL,
            wait_until="domcontentloaded",
            timeout=60000,
        )
        await apply_filters(page)
        
        records = await extract_listing_data(page, limit=30)
        output_path = save_raw_json(records)

        print(records)
        print(f"Saved to {output_path}")
        print("Website opened successfully.")
        print("Press ENTER in the terminal to close the browser.")

        input()

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())