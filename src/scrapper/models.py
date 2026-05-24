import math

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def normalize_blank(value: object) -> object:
    if isinstance(value, float) and math.isnan(value):
        return None

    if isinstance(value, str):
        text = " ".join(value.replace("\xa0", " ").split())
        return text or None

    return value


class ScraperModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @field_validator("*", mode="before")
    @classmethod
    def clean_blank_strings(cls, value: object) -> object:
        return normalize_blank(value)


class ListingRow(ScraperModel):
    bid_id: str
    category: str
    buyer: str
    quantity: int | None = Field(default=None, ge=0)
    bid_value: float | None = Field(default=None, ge=0)
    award_date: str | None = None
    bid_result_link: str | None = None

    @field_validator("quantity", mode="before")
    @classmethod
    def parse_quantity(cls, value: object) -> int | None:
        value = normalize_blank(value)

        if value is None:
            return None

        if isinstance(value, int):
            return value

        if isinstance(value, str):
            digits = "".join(character for character in value if character.isdigit())
            return int(digits) if digits else None

        return value


class VendorRow(ScraperModel):
    bid_id: str
    vendor_name: str
    vendor_rank: str | None = None
    vendor_price: float | None = Field(default=None, ge=0)
    status_flag: str | None = None
    remarks: str | None = None

    @field_validator("vendor_rank")
    @classmethod
    def validate_rank(cls, value: str | None) -> str | None:
        if value is None:
            return None

        if not value.upper().startswith("L"):
            raise ValueError("vendor_rank must use L-ranking, e.g. L1")

        return value.upper()


class BidDetailRow(ListingRow):
    winner_name: str | None = None
    winner_price: float | None = Field(default=None, ge=0)
    num_bidders: int | None = Field(default=None, ge=0)
    error: str | None = None


class ProcessedVendorRow(ScraperModel):
    vendor_name: str
    vendor_rank: str | None = None
    vendor_price: float | None = Field(default=None, ge=0)
    status_flag: str | None = None
    remarks: str | None = None


class ProcessedBidRow(ScraperModel):
    bid_id: str
    category: str
    buyer: str
    quantity: int | None = Field(default=None, ge=0)
    bid_value: float | None = Field(default=None, ge=0)
    award_date: str | None = None
    winner_name: str
    winner_price: float = Field(ge=0)
    num_bidders: int = Field(ge=0)
    l1_l2_gap: float | None = None
    l1_l2_gap_pct: float | None = None
    has_more_than_3_participants: bool
    winner_not_lowest: bool
    has_duplicate_vendor: bool
    status_flag: str | None = None
    vendors: list[ProcessedVendorRow]

    @model_validator(mode="after")
    def check_winner_in_vendor_rows(self) -> "ProcessedBidRow":
        vendor_names = {vendor.vendor_name for vendor in self.vendors}

        if self.winner_name not in vendor_names:
            raise ValueError("winner_name is not present in vendor rows")

        return self


class BadDataRow(ScraperModel):
    bid_id: str | None = None
    reason: str
    row_type: str
    payload: dict
