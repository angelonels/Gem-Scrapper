# GemEdge Assignment Write-Up

The scraper uses Python, Playwright, Pydantic, and pandas. Playwright collects filtered GeM bid listings, follows each `View BID Results` link in parallel, and extracts bid-level winner data plus vendor-level financial and technical evaluation rows. Result pages are opened with JavaScript disabled because the required evaluation tables are server-rendered and the page includes anti-devtools JavaScript that can redirect automation sessions.

Raw data is stored as flat JSON tables: listings, bid results, and vendors. This avoids nested raw files and keeps DataFrame joins simple. The pipeline then loads these rows into pandas DataFrames, validates them with Pydantic schemas, normalizes vendor names, computes L1-L2 pricing gaps, detects duplicate vendors, flags winner-not-lowest anomalies, and separates good and bad records into processed outputs.

The main challenge was inconsistent portal layouts and incomplete public data. Some listing cards lack categories or result links, and some result pages expose partial technical/financial rows. The pipeline does not invent missing procurement values; it keeps those rows in `bad_data.json` with reasons so failures remain auditable.

The scraper would break if GeM changes card selectors, the `View BID Results` URL pattern, or the evaluation table headers. Future improvements would add retry/backoff controls, selector smoke tests, CSV exports, and a small CLI for choosing page count and concurrency.
