# Gem-Scrapper

A small Playwright-based scraper for collecting bid listings from the Government e-Marketplace (GeM) bid portal.

## What it does

- Opens the GeM bids page.
- Applies the configured filters.
- Extracts listing data such as bid number, item category, department, quantity, award date, and bid link.
- Saves raw results to `data/raw/listings_data.json`.

## Requirements

- Python 3.12+
- `uv`

## Setup

```bash
uv sync
uv run playwright install chromium
```

## Run

```bash
uv run python src/scrapper/main.py
```

The scraper opens a browser, collects listings, and writes the output JSON under `data/raw/`.
