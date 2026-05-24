# Gem Scrapper

Gem Scrapper is a Python scraper for the public GeM bid portal. It collects awarded Bid/RA listings, opens each bid result page, extracts winner and vendor pricing data, validates the data, and writes raw and processed JSON files.

This project was built for the GemEdge data extraction assignment.

## What It Does

1. Opens `https://bidplus.gem.gov.in/all-bids`.
2. Applies the Bid/RA and Awarded filters.
3. Extracts bid listing data across paginated results.
4. Opens each `View BID Results` page in parallel.
5. Extracts winner, price, bidder count, vendor ranks, vendor prices, status flags, and remarks.
6. Saves flat raw JSON files.
7. Loads the raw data into pandas DataFrames.
8. Validates rows with Pydantic schemas.
9. Splits the final data into good, bad, and all records.
10. Writes an insights report.

## Data Extracted

Listing fields:

- `bid_id`
- `category`
- `buyer`
- `quantity`
- `bid_value`
- `award_date`
- `bid_result_link`

Bid result fields:

- `winner_name`
- `winner_price`
- `num_bidders`

Vendor fields:

- `vendor_name`
- `vendor_rank`
- `vendor_price`
- `status_flag`
- `remarks`

Derived fields:

- `l1_l2_gap`
- `l1_l2_gap_pct`
- `has_more_than_3_participants`
- `winner_not_lowest`
- `has_duplicate_vendor`

## Pipeline

Some Markdown previewers do not render Mermaid diagrams, so the flow is shown as plain text:

```text
GeM all-bids page
  -> apply Bid/RA + Awarded filters
  -> paginate listing cards
  -> extract flat listing rows
  -> open View BID Results pages in parallel
  -> extract bid result rows
  -> extract vendor rows
  -> write raw JSON files
  -> load pandas DataFrames
  -> validate with Pydantic
  -> compute checks and insights
  -> write processed JSON files
  -> write insights.txt
```

## Output Files

Raw files in `data/raw/`:

- `listings_data.json`: one row per listing card
- `bid_results_data.json`: one row per bid result
- `vendors_data.json`: one row per vendor

Processed files in `data/processed/`:

- `good_data.json`: valid bid records with nested vendor rows
- `bad_data.json`: invalid or suspicious rows with reasons
- `all_data.json`: good records plus bad records
- `insights.txt`: summary of data quality and procurement patterns

Raw files are flat on purpose. This makes DataFrame joins simple. The processed final data can be nested because that is easier to submit and inspect.

## Key Decisions

- Use one naming style everywhere: `bid_id`, `category`, `buyer`, etc.
- Keep raw data flat instead of nested.
- Extract bid result pages in parallel to reduce run time.
- Disable JavaScript on bid result pages because the needed tables are already in the HTML.
- Do not fill missing procurement values with averages or fake values.
- Send incomplete or suspicious rows to `bad_data.json` with a clear reason.
- Use Pydantic before analysis so bad rows do not pollute insights.

## Local Setup

Requirements:

- Python 3.12+
- `uv`

Install dependencies:

```bash
uv sync
```

Install Chromium for Playwright:

```bash
uv run playwright install chromium
```

## Run

```bash
uv run python src/scrapper/main.py
```

The scraper runs headlessly. It writes raw files, processed files, and the insights report.

## Validate

```bash
uv run ruff check src
uv run python -m compileall src
```

## Main Files

- `src/scrapper/filters.py`: applies GeM filters
- `src/scrapper/listings.py`: extracts listing rows
- `src/scrapper/details.py`: extracts bid result and vendor rows
- `src/scrapper/models.py`: Pydantic schemas
- `src/scrapper/processing.py`: DataFrames, validation, good/bad split, insights
- `src/scrapper/storage.py`: JSON file writing

## Notes

- `bid_value` is part of the assignment schema, but the current listing cards do not always expose it.
- Some GeM rows are incomplete. The scraper keeps them in `bad_data.json` instead of guessing missing values.
- The insights are descriptive. They summarize the scraped sample; they do not prove cause and effect.
