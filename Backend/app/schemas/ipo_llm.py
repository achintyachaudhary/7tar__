"""Pydantic schemas for IPO subscription research (LLM output)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


def _empty_str(v: Any) -> str:
    if v is None:
        return ""
    return str(v).strip()


def _optional_float(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _optional_int(v: Any) -> int | None:
    if v is None or v == "":
        return None
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


class BiddingPeriod(BaseModel):
    open_date: str = ""
    close_date: str = ""

    @field_validator("open_date", "close_date", mode="before")
    @classmethod
    def coerce_dates(cls, v: Any) -> str:
        return _empty_str(v)


class PriceBandInr(BaseModel):
    floor: float | None = None
    cap: float | None = None

    @field_validator("floor", "cap", mode="before")
    @classmethod
    def coerce_prices(cls, v: Any) -> float | None:
        return _optional_float(v)


class Pricing(BaseModel):
    price_band_inr: PriceBandInr = Field(default_factory=PriceBandInr)
    final_issue_price_inr: float | None = None

    @field_validator("final_issue_price_inr", mode="before")
    @classmethod
    def coerce_final(cls, v: Any) -> float | None:
        return _optional_float(v)

    @field_validator("price_band_inr", mode="before")
    @classmethod
    def coerce_band(cls, v: Any) -> Any:
        if v is None:
            return {}
        return v


class IssueDetails(BaseModel):
    total_issue_size_crores_inr: float | None = None
    total_shares_offered: int | None = None
    total_shares_bid_for: int | None = None
    issue_type: str = ""

    @field_validator("issue_type", mode="before")
    @classmethod
    def coerce_issue_type(cls, v: Any) -> str:
        return _empty_str(v)

    @field_validator("total_issue_size_crores_inr", mode="before")
    @classmethod
    def coerce_size(cls, v: Any) -> float | None:
        return _optional_float(v)

    @field_validator("total_shares_offered", "total_shares_bid_for", mode="before")
    @classmethod
    def coerce_shares(cls, v: Any) -> int | None:
        return _optional_int(v)


class CategorySubscription(BaseModel):
    shares_offered: int | None = None
    times_subscribed: float | None = None

    @field_validator("shares_offered", mode="before")
    @classmethod
    def coerce_offered(cls, v: Any) -> int | None:
        return _optional_int(v)

    @field_validator("times_subscribed", mode="before")
    @classmethod
    def coerce_times(cls, v: Any) -> float | None:
        return _optional_float(v)


class CategoryBreakdown(BaseModel):
    qualified_institutional_buyers_qib: CategorySubscription | None = None
    non_institutional_investors_nii: CategorySubscription | None = None
    retail_individual_investors_rii: CategorySubscription | None = None
    employee_reservation: CategorySubscription | None = None

    @field_validator(
        "qualified_institutional_buyers_qib",
        "non_institutional_investors_nii",
        "retail_individual_investors_rii",
        "employee_reservation",
        mode="before",
    )
    @classmethod
    def coerce_category(cls, v: Any) -> Any:
        if v is None:
            return None
        return v


class SubscriptionSummary(BaseModel):
    overall_times_subscribed: float | None = None
    category_breakdown: CategoryBreakdown = Field(default_factory=CategoryBreakdown)

    @field_validator("overall_times_subscribed", mode="before")
    @classmethod
    def coerce_overall(cls, v: Any) -> float | None:
        return _optional_float(v)

    @field_validator("category_breakdown", mode="before")
    @classmethod
    def coerce_breakdown(cls, v: Any) -> Any:
        if v is None:
            return {}
        return v


class IpoSubscriptionResearch(BaseModel):
    company_name: str = ""
    ticker_symbol: str = ""
    bidding_period: BiddingPeriod = Field(default_factory=BiddingPeriod)
    pricing: Pricing = Field(default_factory=Pricing)
    issue_details: IssueDetails = Field(default_factory=IssueDetails)
    subscription_summary: SubscriptionSummary = Field(default_factory=SubscriptionSummary)

    @field_validator("company_name", "ticker_symbol", mode="before")
    @classmethod
    def coerce_names(cls, v: Any) -> str:
        return _empty_str(v)

    @field_validator("bidding_period", "pricing", "issue_details", "subscription_summary", mode="before")
    @classmethod
    def coerce_nested(cls, v: Any) -> Any:
        if v is None:
            return {}
        return v


class IpoLlmResearchResponse(BaseModel):
    symbol: str
    provider: str
    fetched_at: str
    data: IpoSubscriptionResearch
    from_cache: bool = False
    status: str = "fetched"


class IpoLlmStatusItem(BaseModel):
    symbol: str
    status: str  # pending | fetched | failed
    fetched_at: str | None = None
    error_message: str | None = None
    overall_times_subscribed: float | None = None


class IpoLlmStatusResponse(BaseModel):
    statuses: list[IpoLlmStatusItem]


class IpoBatchFetchItem(BaseModel):
    symbol: str
    company_name: str | None = None


class IpoBatchFetchRequest(BaseModel):
    items: list[IpoBatchFetchItem]


class IpoBatchFetchResultItem(BaseModel):
    symbol: str
    status: str  # fetched | failed | skipped
    error: str | None = None


class IpoBatchFetchResponse(BaseModel):
    results: list[IpoBatchFetchResultItem]
    fetched_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0
