# Gem Scraper Context

## Domain Terms

- **Listing row**: One bid card from the filtered GeM listing page. Uses canonical keys: `bid_id`, `category`, `buyer`, `quantity`, `bid_value`, `award_date`, and `bid_result_link`.
- **Bid result row**: One bid-level result extracted from the GeM bid result page. Uses canonical keys: `bid_id`, `category`, `buyer`, `quantity`, `bid_value`, `award_date`, `winner_name`, `winner_price`, and `num_bidders`.
- **Vendor row**: One vendor participating in a bid result. Uses canonical keys: `bid_id`, `vendor_name`, `vendor_rank`, `vendor_price`, `status_flag`, and `remarks`.
- **Processed bid row**: A validated bid result with nested vendor rows plus derived analysis fields such as `l1_l2_gap`, `has_more_than_3_participants`, and anomaly flags.
- **Bad data row**: A validation failure or anomaly row with `bid_id`, `row_type`, `reason`, and original `payload`.

## Naming Rule

Use assignment-facing names throughout raw and processed data. Do not use portal-only names such as `bid_ra_number`, `item_category`, or `buyer_department` outside compatibility adapters.
