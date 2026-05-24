import asyncio
import re
from typing import Any

from playwright.async_api import Browser, BrowserContext, Page, TimeoutError as PlaywrightTimeoutError


BID_RESULT_TIMEOUT = 60_000
RESULT_TABLE_SELECTOR = "table.table"
DEFAULT_DETAIL_CONCURRENCY = 8


def clean_text(value: str | None) -> str | None:
    if value is None:
        return None

    text = " ".join(value.replace("\xa0", " ").split())

    return text or None


def parse_price(value: str | None) -> float | None:
    if not value:
        return None

    match = re.search(r"[\d,]+(?:\.\d+)?", value)

    if not match:
        return None

    return float(match.group(0).replace(",", ""))


def extract_bid_result_id(result_link: str | None) -> str | None:
    if not result_link:
        return None

    match = re.search(r"/getBidResultView/(\d+)", result_link)

    if not match:
        return None

    return match.group(1)


async def get_result_page_tables(page: Page) -> list[dict[str, Any]]:
    return await page.locator(RESULT_TABLE_SELECTOR).evaluate_all(
        """
        tables => tables.map((table) => {
            const headerCells = Array.from(table.querySelectorAll("tr:first-child th, thead th"));
            const headers = headerCells.map((cell) => cell.innerText.trim().replace(/\\s+/g, " "));
            const rows = Array.from(table.querySelectorAll("tr"))
                .map((row) => Array.from(row.querySelectorAll("th, td"))
                    .map((cell) => cell.innerText.trim().replace(/\\s+/g, " ")))
                .filter((row) => row.length > 0);

            return { headers, rows };
        })
        """
    )


def row_dict(headers: list[str], row: list[str]) -> dict[str, str | None]:
    data = {}

    for index, header in enumerate(headers):
        data[header] = clean_text(row[index] if index < len(row) else None)

    if len(row) > len(headers):
        data["Remarks"] = clean_text(" ".join(row[len(headers):]))

    return data


def normalize_vendor_name(value: str | None) -> str | None:
    text = clean_text(value)

    if not text:
        return None

    text = re.sub(r"\s+Under PMA$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\( MSE Social Category:[^)]+\)", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\(MSE\)|\( MSE\)", "", text, flags=re.IGNORECASE)

    return clean_text(text)


def parse_technical_table(table: dict[str, Any]) -> list[dict[str, str | None]]:
    headers = table.get("headers") or []
    rows = table.get("rows") or []
    sellers = []

    for row in rows[1:]:
        data = row_dict(headers, row)
        sellers.append(
            {
                "vendor_name": normalize_vendor_name(data.get("Seller Name")),
                "status_flag": data.get("Status"),
                "remarks": data.get("Remarks"),
            }
        )

    return sellers


def parse_financial_table(table: dict[str, Any]) -> list[dict[str, Any]]:
    headers = table.get("headers") or []
    rows = table.get("rows") or []
    vendors = []

    for row in rows[1:]:
        data = row_dict(headers, row)
        vendors.append(
            {
                "vendor_name": normalize_vendor_name(data.get("Seller Name")),
                "vendor_price": parse_price(data.get("Total Price")),
                "vendor_rank": data.get("Rank"),
                "remarks": data.get("Remarks"),
            }
        )

    return vendors


def find_table(tables: list[dict[str, Any]], required_headers: set[str]) -> dict[str, Any] | None:
    for table in tables:
        headers = set(table.get("headers") or [])

        if required_headers.issubset(headers):
            return table

    return None


def summarize_result(
    technical_vendors: list[dict[str, str | None]],
    financial_vendors: list[dict[str, Any]],
) -> dict[str, Any]:
    winning_vendor = next(
        (vendor for vendor in financial_vendors if vendor.get("vendor_rank") == "L1"),
        financial_vendors[0] if financial_vendors else None,
    )

    disqualified_statuses = ("disqualified", "rejected", "not qualified", "technically disqualified")
    technical_status_by_vendor = {
        vendor["vendor_name"]: vendor
        for vendor in technical_vendors
        if vendor.get("vendor_name")
    }
    vendors = []

    for vendor in financial_vendors:
        technical_vendor = technical_status_by_vendor.get(vendor.get("vendor_name"))
        vendors.append(
            {
                "vendor_name": vendor.get("vendor_name"),
                "vendor_rank": vendor.get("vendor_rank"),
                "vendor_price": vendor.get("vendor_price"),
                "status_flag": technical_vendor.get("status_flag") if technical_vendor else None,
                "remarks": technical_vendor.get("remarks") if technical_vendor else vendor.get("remarks"),
            }
        )

    for vendor in technical_vendors:
        if vendor.get("vendor_name") in {item.get("vendor_name") for item in vendors}:
            continue

        status_flag = vendor.get("status_flag")

        if status_flag and any(status in status_flag.lower() for status in disqualified_statuses):
            vendors.append(
                {
                    "vendor_name": vendor.get("vendor_name"),
                    "vendor_rank": None,
                    "vendor_price": None,
                    "status_flag": status_flag,
                    "remarks": vendor.get("remarks"),
                }
            )

    return {
        "winner_name": winning_vendor.get("vendor_name") if winning_vendor else None,
        "winner_price": winning_vendor.get("vendor_price") if winning_vendor else None,
        "num_bidders": len(technical_vendors) or len(financial_vendors),
        "vendors": vendors,
    }


async def extract_bid_result_details_from_context(
    context: BrowserContext,
    result_link: str,
) -> dict[str, Any]:
    page = await context.new_page()

    try:
        await page.goto(result_link, wait_until="domcontentloaded", timeout=BID_RESULT_TIMEOUT)
        await page.wait_for_selector(RESULT_TABLE_SELECTOR, state="attached", timeout=BID_RESULT_TIMEOUT)

        tables = await get_result_page_tables(page)
        technical_table = find_table(
            tables,
            {"S.No.", "Seller Name", "Participated On", "Status"},
        )
        financial_table = find_table(
            tables,
            {"S.No.", "Seller Name", "Total Price", "Rank"},
        )

        technical_vendors = parse_technical_table(technical_table) if technical_table else []
        financial_vendors = parse_financial_table(financial_table) if financial_table else []

        return {
            **summarize_result(technical_vendors, financial_vendors),
        }

    except PlaywrightTimeoutError as error:
        return {
            "error": f"Timed out loading bid result details: {error}",
        }

    finally:
        await page.close()


async def extract_bid_result_details(browser: Browser, result_link: str) -> dict[str, Any]:
    context = await browser.new_context(
        ignore_https_errors=True,
        java_script_enabled=False,
        extra_http_headers={"Referer": "https://bidplus.gem.gov.in/all-bids"},
    )

    try:
        return await extract_bid_result_details_from_context(context, result_link)
    finally:
        await context.close()


def structure_record(record: dict, details: dict[str, Any] | None) -> dict[str, Any]:
    details = details or {}

    return {
        "bid_id": record.get("bid_ra_number"),
        "category": record.get("item_category"),
        "buyer": record.get("buyer_department"),
        "quantity": record.get("quantity"),
        "bid_value": record.get("bid_value"),
        "award_date": record.get("award_date"),
        "winner_name": details.get("winner_name"),
        "winner_price": details.get("winner_price"),
        "num_bidders": details.get("num_bidders"),
        "vendors": details.get("vendors", []),
        **({"error": details["error"]} if details.get("error") else {}),
    }


async def enrich_records_with_bid_results(
    browser: Browser,
    records: list[dict],
    concurrency: int = DEFAULT_DETAIL_CONCURRENCY,
) -> list[dict]:
    context = await browser.new_context(
        ignore_https_errors=True,
        java_script_enabled=False,
        extra_http_headers={"Referer": "https://bidplus.gem.gov.in/all-bids"},
    )
    semaphore = asyncio.Semaphore(concurrency)

    async def enrich_one(index: int, record: dict) -> dict[str, Any]:
        result_link = record.get("bid_result_link")

        if not result_link:
            return structure_record(record, None)

        print(f"Extracting bid result {index}/{len(records)}: {record.get('bid_ra_number')}")

        async with semaphore:
            details = await extract_bid_result_details_from_context(context, result_link)

        return structure_record(record, details)

    try:
        tasks = [
            enrich_one(index, record)
            for index, record in enumerate(records, start=1)
        ]

        return await asyncio.gather(*tasks)
    finally:
        await context.close()
