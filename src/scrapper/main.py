import asyncio
from playwright.async_api import async_playwright
from details import enrich_records_with_bid_results
from filters import apply_filters
from listings import extract_listing_data
from processing import process_scraped_data
from storage import RAW_DIR, save_json
URL = "https://bidplus.gem.gov.in/all-bids"

async def main() -> None:
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,

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

        listing_records = await extract_listing_data(page)
        bid_records, vendor_records = await enrich_records_with_bid_results(browser, listing_records)
        listings_output_path = save_json(listing_records, RAW_DIR / "listings_data.json")
        bids_output_path = save_json(bid_records, RAW_DIR / "bid_results_data.json")
        vendors_output_path = save_json(vendor_records, RAW_DIR / "vendors_data.json")
        processed_paths = process_scraped_data(listing_records, bid_records, vendor_records)

        print(f"Saved listings to {listings_output_path}")
        print(f"Saved bid results to {bids_output_path}")
        print(f"Saved vendors to {vendors_output_path}")
        print(f"Saved processed outputs to {processed_paths}")
        print("Website opened successfully.")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
