"""Pydantic response schemas."""

from pydantic import BaseModel, Field


class ShareholdingInfo(BaseModel):
    promoter_holding_pct: float | None = None
    fii_holding_pct: float | None = None
    dii_holding_pct: float | None = None
    public_holding_pct: float | None = None
    mutual_fund_holding_pct: float | None = None
    institutional_holding_pct: float | None = None
    holding_as_of: str | None = None
    holding_source: str | None = None


class StockSignal(BaseModel):
    symbol: str
    price: float
    change_5d_pct: float | None = None
    change_20d_pct: float | None = None
    rsi: float | None = None
    macd: float | None = None
    macd_signal: float | None = None
    macd_histogram: float | None = None
    sma_20: float | None = None
    sma_50: float | None = None
    score: int
    overall_score: float | None = None
    signals: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    trend: str = "neutral"


class PriceBar(BaseModel):
    date: str
    close: float


class OhlcBar(BaseModel):
    time: str | int
    open: float
    high: float
    low: float
    close: float
    volume: int | None = None


class ChartResponse(BaseModel):
    symbol: str
    timeframe: str
    interval: str
    tv_interval: str
    bars: list[OhlcBar] = Field(default_factory=list)


class StockDetail(StockSignal):
    history: list[PriceBar] = Field(default_factory=list)


class ShareholdingPeriod(BaseModel):
    as_of: str
    label: str
    promoter_holding_pct: float | None = None
    fii_holding_pct: float | None = None
    dii_holding_pct: float | None = None
    public_holding_pct: float | None = None
    retail_and_others_pct: float | None = None
    mutual_fund_holding_pct: float | None = None


class FinancialPeriod(BaseModel):
    period: str
    label: str
    revenue_cr: float | None = None
    profit_cr: float | None = None


class FinancialSummary(BaseModel):
    revenue_growth_yoy_pct: float | None = None
    revenue_cagr_3y_pct: float | None = None
    profit_growth_yoy_pct: float | None = None
    profit_cagr_3y_pct: float | None = None


class StockInsightsResponse(BaseModel):
    symbol: str
    company_name: str
    sector: str | None = None
    industry: str | None = None
    market_cap_cr: float | None = None
    market_cap_category: str | None = None
    overall_score: float | None = None
    shareholding: list[ShareholdingPeriod] = Field(default_factory=list)
    financials_quarterly: list[FinancialPeriod] = Field(default_factory=list)
    financials_yearly: list[FinancialPeriod] = Field(default_factory=list)
    revenue_growth_yoy_pct: float | None = None
    revenue_cagr_3y_pct: float | None = None
    profit_growth_yoy_pct: float | None = None
    profit_cagr_3y_pct: float | None = None
    last_profile_updated: str | None = None
    last_holdings_updated: str | None = None
    last_financials_updated: str | None = None


class ScanResponse(BaseModel):
    scanned_at: str
    index: str
    index_label: str
    total_scanned: int
    total_matched: int
    min_score: int
    results: list[StockSignal]


class IndexOption(BaseModel):
    id: str
    label: str
    description: str
    slow_scan: bool = False


class IndicesResponse(BaseModel):
    indices: list[IndexOption]


class IpoListing(BaseModel):
    symbol: str
    company_name: str
    security_type: str = ""
    ipo_start_date: str = ""
    ipo_end_date: str = ""
    listing_date: str
    listing_date_display: str = ""
    issue_price: float | None = None
    price_range: str = ""
    yf_symbol: str | None = None
    listing_open: float | None = None
    listing_close: float | None = None
    listing_high: float | None = None
    current_price: float | None = None
    listing_day_gain_pct: float | None = None
    gain_vs_issue_pct: float | None = None
    gain_vs_listing_close_pct: float | None = None
    gain_listing_open_to_current_pct: float | None = None
    status: str = "listed"


class IpoTrackResponse(BaseModel):
    scanned_at: str
    months: int
    total_listed: int
    with_market_data: int
    results: list[IpoListing]


class HealthResponse(BaseModel):
    status: str = "ok"
