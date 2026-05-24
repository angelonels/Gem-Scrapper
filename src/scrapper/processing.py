from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd
from pydantic import ValidationError

try:
    from .models import BadDataRow, BidDetailRow, ListingRow, ProcessedBidRow, VendorRow
    from .storage import PROCESSED_DIR, save_json
except ImportError:
    from models import BadDataRow, BidDetailRow, ListingRow, ProcessedBidRow, VendorRow
    from storage import PROCESSED_DIR, save_json


def validation_error_text(error: ValidationError) -> str:
    return "; ".join(
        f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}"
        for item in error.errors()
    )


def validate_rows(model: type, rows: list[dict], row_type: str) -> tuple[list[dict], list[dict]]:
    valid_rows = []
    bad_rows = []

    for row in rows:
        try:
            valid_rows.append(model.model_validate(row).model_dump())
        except ValidationError as error:
            bad_rows.append(
                BadDataRow(
                    bid_id=row.get("bid_id"),
                    row_type=row_type,
                    reason=validation_error_text(error),
                    payload=row,
                ).model_dump()
            )

    return valid_rows, bad_rows


def normalize_listing_rows(rows: list[dict]) -> list[dict]:
    normalized_rows = []

    for row in rows:
        normalized_rows.append(
            {
                "bid_id": row.get("bid_id") or row.get("bid_ra_number"),
                "category": row.get("category") or row.get("item_category"),
                "buyer": row.get("buyer") or row.get("buyer_department"),
                "quantity": row.get("quantity"),
                "bid_value": row.get("bid_value"),
                "award_date": row.get("award_date"),
                "bid_result_link": row.get("bid_result_link"),
            }
        )

    return normalized_rows


def vendor_status_is_bad(status: str | None) -> bool:
    if not isinstance(status, str) or not status:
        return False

    bad_statuses = ("disqualified", "rejected", "not qualified", "technically disqualified")
    return any(bad_status in status.lower() for bad_status in bad_statuses)


def build_processed_bid(
    listing: dict[str, Any],
    bid_detail: dict[str, Any],
    vendors: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    bid_id = listing["bid_id"]

    if not bid_detail.get("winner_name"):
        return None, BadDataRow(
            bid_id=bid_id,
            row_type="bid",
            reason="missing winner_name",
            payload={**listing, **bid_detail, "vendors": vendors},
        ).model_dump()

    if bid_detail.get("winner_price") is None:
        return None, BadDataRow(
            bid_id=bid_id,
            row_type="bid",
            reason="missing winner_price",
            payload={**listing, **bid_detail, "vendors": vendors},
        ).model_dump()

    ranked_vendors = [
        vendor
        for vendor in vendors
        if vendor.get("vendor_rank") and vendor.get("vendor_price") is not None
    ]
    l1_vendor = next(
        (vendor for vendor in ranked_vendors if vendor.get("vendor_rank") == "L1"),
        None,
    )
    l2_vendor = next(
        (vendor for vendor in ranked_vendors if vendor.get("vendor_rank") == "L2"),
        None,
    )
    valid_prices = [
        vendor["vendor_price"]
        for vendor in ranked_vendors
        if not vendor_status_is_bad(vendor.get("status_flag"))
    ]
    lowest_price = min(valid_prices) if valid_prices else None
    winner_price = bid_detail["winner_price"]
    l1_l2_gap = None
    l1_l2_gap_pct = None

    if l1_vendor and l2_vendor:
        l1_l2_gap = l2_vendor["vendor_price"] - l1_vendor["vendor_price"]

        if l1_vendor["vendor_price"]:
            l1_l2_gap_pct = (l1_l2_gap / l1_vendor["vendor_price"]) * 100

    vendor_names = [
        vendor["vendor_name"]
        for vendor in vendors
        if vendor.get("vendor_name")
    ]
    processed_vendors = [
        {
            key: vendor.get(key)
            for key in ["vendor_name", "vendor_rank", "vendor_price", "status_flag", "remarks"]
        }
        for vendor in vendors
    ]
    duplicate_vendors = [
        vendor_name
        for vendor_name, count in Counter(vendor_names).items()
        if count > 1
    ]
    winner_not_lowest = (
        lowest_price is not None
        and abs(float(winner_price) - float(lowest_price)) > 0.01
    )
    status_flag = "bad" if winner_not_lowest or duplicate_vendors else "good"

    listing_fields = {
        key: listing.get(key)
        for key in ["bid_id", "category", "buyer", "quantity", "bid_value", "award_date"]
    }

    processed_row = {
        **listing_fields,
        "winner_name": bid_detail["winner_name"],
        "winner_price": winner_price,
        "num_bidders": bid_detail.get("num_bidders") or len(vendors),
        "l1_l2_gap": l1_l2_gap,
        "l1_l2_gap_pct": l1_l2_gap_pct,
        "has_more_than_3_participants": (bid_detail.get("num_bidders") or len(vendors)) > 3,
        "winner_not_lowest": winner_not_lowest,
        "has_duplicate_vendor": bool(duplicate_vendors),
        "status_flag": status_flag,
        "vendors": processed_vendors,
    }

    try:
        validated_row = ProcessedBidRow.model_validate(processed_row).model_dump()
    except ValidationError as error:
        return None, BadDataRow(
            bid_id=bid_id,
            row_type="bid",
            reason=validation_error_text(error),
            payload=processed_row,
        ).model_dump()

    if status_flag == "bad":
        return None, BadDataRow(
            bid_id=bid_id,
            row_type="bid",
            reason="; ".join(
                reason
                for reason in [
                    "winner_not_lowest" if winner_not_lowest else None,
                    "duplicate_vendor" if duplicate_vendors else None,
                ]
                if reason
            ),
            payload=validated_row,
        ).model_dump()

    return validated_row, None


def build_dataframes(
    listing_rows: list[dict],
    bid_rows: list[dict],
    vendor_rows: list[dict],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, list[dict]]:
    normalized_listings = normalize_listing_rows(listing_rows)
    valid_listings, bad_listing_rows = validate_rows(ListingRow, normalized_listings, "listing")
    valid_bids, bad_bid_detail_rows = validate_rows(BidDetailRow, bid_rows, "bid_detail")
    valid_vendors, bad_vendor_rows = validate_rows(VendorRow, vendor_rows, "vendor")

    listing_df = pd.DataFrame(valid_listings)
    bid_df = pd.DataFrame(valid_bids)
    vendor_df = pd.DataFrame(valid_vendors)

    listing_df = listing_df.where(pd.notnull(listing_df), None)
    bid_df = bid_df.where(pd.notnull(bid_df), None)
    vendor_df = vendor_df.where(pd.notnull(vendor_df), None)

    bad_rows = bad_listing_rows + bad_bid_detail_rows + bad_vendor_rows

    return listing_df, bid_df, vendor_df, bad_rows


def assemble_processed_data(
    listing_df: pd.DataFrame,
    bid_df: pd.DataFrame,
    vendor_df: pd.DataFrame,
    initial_bad_rows: list[dict],
) -> tuple[list[dict], list[dict], list[dict], dict[str, Any]]:
    bad_rows = list(initial_bad_rows)
    good_rows = []
    all_rows = [
        {
            "bid_id": row.get("bid_id"),
            "status_flag": "bad",
            "row_type": row.get("row_type"),
            "reason": row.get("reason"),
            "payload": row.get("payload"),
        }
        for row in initial_bad_rows
    ]

    if listing_df.empty:
        return good_rows, bad_rows, all_rows, build_insights(good_rows, bad_rows, vendor_df)

    merged_df = listing_df.merge(
        bid_df.drop(columns=["category", "buyer", "quantity", "bid_value", "award_date", "bid_result_link"], errors="ignore"),
        on="bid_id",
        how="left",
    )

    for listing in merged_df.to_dict(orient="records"):
        bid_id = listing["bid_id"]
        vendors = vendor_df[vendor_df["bid_id"] == bid_id].to_dict(orient="records") if not vendor_df.empty else []
        processed_row, bad_row = build_processed_bid(listing, listing, vendors)

        if processed_row:
            good_rows.append(processed_row)
            all_rows.append(processed_row)
        elif bad_row:
            bad_rows.append(bad_row)
            all_rows.append(
                {
                    "bid_id": bid_id,
                    "status_flag": "bad",
                    "reason": bad_row["reason"],
                    "payload": bad_row["payload"],
                }
            )

    insights = build_insights(good_rows, bad_rows, vendor_df)

    return good_rows, bad_rows, all_rows, insights


def build_insights(
    good_rows: list[dict],
    bad_rows: list[dict],
    vendor_df: pd.DataFrame,
) -> dict[str, Any]:
    bid_bad_rows = [row for row in bad_rows if row.get("row_type") == "bid"]
    listing_bad_rows = [row for row in bad_rows if row.get("row_type") == "listing"]
    bid_detail_bad_rows = [row for row in bad_rows if row.get("row_type") == "bid_detail"]
    processable_bid_count = len(good_rows) + len(bid_bad_rows)
    extracted_listing_count = processable_bid_count + len(listing_bad_rows)
    rows_with_l2_gap = [
        row
        for row in good_rows
        if row.get("l1_l2_gap") is not None
    ]
    winner_counts = Counter(row["winner_name"] for row in good_rows if row.get("winner_name"))
    duplicate_vendor_rows = 0

    if not vendor_df.empty:
        duplicate_vendor_rows = int(vendor_df.duplicated(subset=["bid_id", "vendor_name"]).sum())

    bidder_counts = [row["num_bidders"] for row in good_rows if row.get("num_bidders") is not None]
    l1_l2_gap_values = [row["l1_l2_gap"] for row in rows_with_l2_gap]
    l1_l2_gap_pct_values = [
        row["l1_l2_gap_pct"]
        for row in rows_with_l2_gap
        if row.get("l1_l2_gap_pct") is not None
    ]
    disqualified_vendor_rows = []

    if not vendor_df.empty and "status_flag" in vendor_df.columns:
        status_series = vendor_df["status_flag"].fillna("").astype(str).str.lower()
        disqualified_vendor_rows = vendor_df[
            status_series.str.contains("disqualified|rejected|not qualified", regex=True)
        ].to_dict(orient="records")

    bad_reason_counts = Counter(row.get("reason", "unknown") for row in bad_rows)
    bad_row_type_counts = Counter(row.get("row_type", "unknown") for row in bad_rows)
    buyer_counts = Counter(row["buyer"] for row in good_rows if row.get("buyer"))
    category_counts = Counter(row["category"] for row in good_rows if row.get("category"))
    tightest_l1_l2_gaps = sorted(
        rows_with_l2_gap,
        key=lambda row: row["l1_l2_gap"],
    )[:5]
    widest_l1_l2_gaps = sorted(
        rows_with_l2_gap,
        key=lambda row: row["l1_l2_gap"],
        reverse=True,
    )[:5]

    return {
        "total_good_bids": len(good_rows),
        "total_bad_rows": len(bad_rows),
        "extracted_listing_count": extracted_listing_count,
        "processable_bid_count": processable_bid_count,
        "bid_detail_failure_count": len(bid_detail_bad_rows),
        "good_bid_rate": (
            round(len(good_rows) / processable_bid_count * 100, 2)
            if processable_bid_count
            else 0
        ),
        "bad_row_type_counts": dict(bad_row_type_counts),
        "top_bad_reasons": dict(bad_reason_counts.most_common(8)),
        "percent_bids_more_than_3_participants": (
            round(
                sum(row["has_more_than_3_participants"] for row in good_rows) / len(good_rows) * 100,
                2,
            )
            if good_rows
            else 0
        ),
        "average_l1_l2_gap": (
            round(sum(row["l1_l2_gap"] for row in rows_with_l2_gap) / len(rows_with_l2_gap), 2)
            if rows_with_l2_gap
            else None
        ),
        "median_l1_l2_gap": (
            round(float(pd.Series(l1_l2_gap_values).median()), 2)
            if l1_l2_gap_values
            else None
        ),
        "max_l1_l2_gap": round(max(l1_l2_gap_values), 2) if l1_l2_gap_values else None,
        "min_l1_l2_gap": round(min(l1_l2_gap_values), 2) if l1_l2_gap_values else None,
        "average_l1_l2_gap_pct": (
            round(sum(l1_l2_gap_pct_values) / len(l1_l2_gap_pct_values), 2)
            if l1_l2_gap_pct_values
            else None
        ),
        "average_num_bidders": (
            round(sum(bidder_counts) / len(bidder_counts), 2)
            if bidder_counts
            else None
        ),
        "max_num_bidders": max(bidder_counts) if bidder_counts else None,
        "single_bidder_bids": sum(1 for count in bidder_counts if count == 1),
        "top_buyers": dict(buyer_counts.most_common(8)),
        "top_categories": dict(category_counts.most_common(8)),
        "repeat_winners": {
            winner: count
            for winner, count in winner_counts.items()
            if count > 1
        },
        "duplicate_vendor_rows": duplicate_vendor_rows,
        "disqualified_vendor_rows": disqualified_vendor_rows,
        "tightest_l1_l2_gaps": [
            {
                "bid_id": row["bid_id"],
                "winner_name": row["winner_name"],
                "winner_price": row["winner_price"],
                "l1_l2_gap": row["l1_l2_gap"],
                "l1_l2_gap_pct": row["l1_l2_gap_pct"],
            }
            for row in tightest_l1_l2_gaps
        ],
        "widest_l1_l2_gaps": [
            {
                "bid_id": row["bid_id"],
                "winner_name": row["winner_name"],
                "winner_price": row["winner_price"],
                "l1_l2_gap": row["l1_l2_gap"],
                "l1_l2_gap_pct": row["l1_l2_gap_pct"],
            }
            for row in widest_l1_l2_gaps
        ],
    }


def write_insights(insights: dict[str, Any], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "GeM Scraper Insights",
        "",
        "1. Coverage and Data Quality",
        f"- Listing rows extracted: {insights['extracted_listing_count']}",
        f"- Bid rows processable after listing validation: {insights['processable_bid_count']}",
        f"- Bid-detail extraction failures: {insights['bid_detail_failure_count']}",
        f"- Good processed bids from processable rows: {insights['total_good_bids']} ({insights['good_bid_rate']}%)",
        f"- Bad rows/anomalies: {insights['total_bad_rows']}",
        f"- Duplicate vendor rows detected: {insights['duplicate_vendor_rows']}",
        "",
        "Bad row types:",
        *format_key_value_lines(insights["bad_row_type_counts"]),
        "",
        "Top validation/anomaly reasons:",
        *format_key_value_lines(insights["top_bad_reasons"]),
        "",
        "2. Competition Profile",
        f"- Average bidders per good bid: {insights['average_num_bidders']}",
        f"- Maximum bidders in a good bid: {insights['max_num_bidders']}",
        f"- Single-bidder good bids: {insights['single_bidder_bids']}",
        f"- Bids with more than 3 participants: {insights['percent_bids_more_than_3_participants']}%",
        "",
        "3. L1-L2 Pricing Spread",
        f"- Average L1-L2 gap: {insights['average_l1_l2_gap']}",
        f"- Median L1-L2 gap: {insights['median_l1_l2_gap']}",
        f"- Minimum L1-L2 gap: {insights['min_l1_l2_gap']}",
        f"- Maximum L1-L2 gap: {insights['max_l1_l2_gap']}",
        f"- Average L1-L2 gap percent: {insights['average_l1_l2_gap_pct']}%",
        "",
        "Tightest L1-L2 gaps:",
        *format_bid_gap_lines(insights["tightest_l1_l2_gaps"]),
        "",
        "Widest L1-L2 gaps:",
        *format_bid_gap_lines(insights["widest_l1_l2_gaps"]),
        "",
        "4. Buyer and Category Concentration",
        "Top buyers:",
        *format_key_value_lines(insights["top_buyers"]),
        "",
        "Top categories:",
        *format_key_value_lines(insights["top_categories"]),
        "",
        "5. Repeat Winners",
        "Repeat winners:",
    ]

    repeat_winners = insights["repeat_winners"]

    if repeat_winners:
        lines.extend(f"- {winner}: {count}" for winner, count in repeat_winners.items())
    else:
        lines.append("- None")

    lines.extend(
        [
            "",
            "6. Technical Evaluation Flags",
            f"- Disqualified/rejected vendor rows: {len(insights['disqualified_vendor_rows'])}",
        ]
    )

    if insights["disqualified_vendor_rows"]:
        lines.extend(
            f"- {row.get('bid_id')}: {row.get('vendor_name')} | {row.get('status_flag')} | {row.get('remarks')}"
            for row in insights["disqualified_vendor_rows"][:10]
        )
    else:
        lines.append("- None observed in the validated vendor table")

    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return output_path


def format_key_value_lines(values: dict[str, Any]) -> list[str]:
    if not values:
        return ["- None"]

    return [f"- {key}: {value}" for key, value in values.items()]


def format_bid_gap_lines(rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return ["- None"]

    return [
        (
            f"- {row['bid_id']}: {row['winner_name']} won at {row['winner_price']} "
            f"with L1-L2 gap {round(row['l1_l2_gap'], 2)} "
            f"({round(row['l1_l2_gap_pct'], 2)}%)"
        )
        for row in rows
    ]


def process_scraped_data(
    listing_rows: list[dict],
    bid_rows: list[dict],
    vendor_rows: list[dict],
) -> dict[str, Path]:
    listing_df, bid_df, vendor_df, bad_rows = build_dataframes(listing_rows, bid_rows, vendor_rows)
    good_rows, final_bad_rows, all_rows, insights = assemble_processed_data(
        listing_df,
        bid_df,
        vendor_df,
        bad_rows,
    )

    return {
        "good_data": save_json(good_rows, PROCESSED_DIR / "good_data.json"),
        "bad_data": save_json(final_bad_rows, PROCESSED_DIR / "bad_data.json"),
        "all_data": save_json(all_rows, PROCESSED_DIR / "all_data.json"),
        "insights": write_insights(insights, PROCESSED_DIR / "insights.txt"),
    }
