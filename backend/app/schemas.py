"""Pydantic request/response schemas for the REST API."""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
class LoginRequest(BaseModel):
    username: str
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    is_admin: bool = False
    is_active: bool = True
    created_at: datetime | None = None


class UserCreate(BaseModel):
    """Create an authorized user (admin only)."""

    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9._-]+$")
    password: str = Field(min_length=8, max_length=128)
    is_admin: bool = False


class UserUpdate(BaseModel):
    """Partial update of a user (admin only); omit a field to leave it unchanged."""

    password: str | None = Field(default=None, min_length=8, max_length=128)
    is_active: bool | None = None
    is_admin: bool | None = None


# ---------------------------------------------------------------------------
# API credential management
# ---------------------------------------------------------------------------
class CredentialUpsert(BaseModel):
    provider: str = Field(default="alpaca", description="alpaca | finnhub | polygon | fred")
    api_key: str = Field(min_length=1, max_length=512)
    secret_key: str | None = Field(default=None, max_length=512)
    is_paper: bool = True
    extra: dict | None = None


class CredentialOut(BaseModel):
    provider: str
    has_key: bool
    key_masked: str | None = None
    secret_masked: str | None = None
    is_paper: bool | None = None
    updated_at: datetime | None = None


class TestConnectionRequest(BaseModel):
    provider: str = "alpaca"


class TestConnectionResult(BaseModel):
    provider: str
    ok: bool
    message: str
    detail: dict | None = None


class ProviderStatus(BaseModel):
    provider: str
    configured: bool
    source: str  # env | database | none


class SettingsResponse(BaseModel):
    alpaca: CredentialOut | None = None
    providers: list[ProviderStatus] = []
    data_provider: str = "auto"
    environment_variables_present: bool = False


# ---------------------------------------------------------------------------
# Signals
# ---------------------------------------------------------------------------
class SignalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticker: str
    name: str | None = None
    date: date
    type: str  # BUY | SELL
    setup: str  # UC1 | UC2 | DC1 | DC2 | UR1 | DR1 | UR2 | DR2
    timeframe: str = "DAILY"  # DAILY | WEEKLY | MONTHLY
    entry: float
    target: float
    stop: float
    confidence: float
    price: float
    sector: str | None = None
    confidence_components: dict | None = None
    triggered_rules: list | None = None
    event_flags: dict | None = None
    option_recommendation: dict | None = None
    # LLM research agent output: sentiment, risk_flags, confidence_delta,
    # adjusted_confidence, rationale, model, created_at.
    annotation: dict | None = None
    # Retrospective result: status (TARGET_HIT/STOP_HIT/OPEN/EXPIRED), exit
    # price, profit/loss percentage, and how long the idea took.
    outcome: dict | None = None


class SignalFilters(BaseModel):
    type: str | None = None  # BUY | SELL
    setup: str | None = None  # UC1 | UC2 | DC1 | DC2 | UR1 | DR1 | UR2 | DR2
    timeframe: str | None = None  # DAILY | WEEKLY | MONTHLY
    sector: str | None = None
    min_confidence: float | None = Field(default=None, ge=0, le=100)
    exclude_earnings_week: bool = False
    exclude_macro_risk: bool = False
    min_price: float | None = None
    max_price: float | None = None
    ticker: str | None = None


class SignalListResponse(BaseModel):
    signals: list[SignalOut]
    total: int
    limit: int
    offset: int
    summary: dict
    # True when the payload is the synthetic demo dataset served to visitors
    # who are not signed in.
    demo: bool = False


class SummaryResponse(BaseModel):
    total_buys: int
    total_sells: int
    total_continuation: int = 0
    total_reversal: int = 0
    setup_counts: dict[str, int] = {}
    avg_confidence: float
    high_confidence_count: int
    regime: str | None = None
    vix: float | None = None
    upcoming_macro_events: int = 0
    earnings_risk_count: int = 0
    generated_at: date | None = None


# ---------------------------------------------------------------------------
# Macro / earnings
# ---------------------------------------------------------------------------
class MacroEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    datetime: datetime
    importance: str
    sentiment: str = "neutral"
    category: str | None = None
    country: str = "US"
    forecast: str | None = None
    previous: str | None = None
    actual: str | None = None


class EarningsEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticker: str
    report_date: date
    fiscal_quarter: str | None = None
    eps_estimate: float | None = None
    eps_actual: float | None = None
    revenue_estimate: float | None = None


class MacroSnapshotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    date: date
    regime: str
    spy_close: float | None = None
    spy_ma200: float | None = None
    vix: float | None = None
    vix_term_structure: float | None = None
    ten_year_yield: float | None = None
    fed_funds_rate: float | None = None
    sector_relative_strength: dict | None = None


class MacroDashboardOut(BaseModel):
    snapshot: MacroSnapshotOut | None = None
    macro_events: list[MacroEventOut] = []
    earnings: list[EarningsEventOut] = []
    sector_heatmap: dict[str, float] = {}
    demo: bool = False


# ---------------------------------------------------------------------------
# Charts / signal detail
# ---------------------------------------------------------------------------
class BarOut(BaseModel):
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: float


class OptionContractOut(BaseModel):
    symbol: str
    strike: float
    expiry: date | None = None
    bid: float | None = None
    ask: float | None = None
    last: float | None = None
    open_interest: int | None = None
    implied_volatility: float | None = None


class SignalDetailOut(BaseModel):
    signal: SignalOut
    bars: list[BarOut]
    indicators: dict = {}
    doji_highlight: bool = False
    option_chain: list[OptionContractOut] = []
    demo: bool = False


class AccuracyResponse(BaseModel):
    """Retrospective hit rate: how often picks reached target rather than stop."""

    timeframe: str | None = None
    evaluated: int
    target_hit: int
    stop_hit: int
    open: int
    expired: int
    decided: int
    win_rate_pct: float | None = None
    avg_pnl_pct: float | None = None
    avg_win_pct: float | None = None
    avg_loss_pct: float | None = None
    by_setup: list[dict] = []


# ---------------------------------------------------------------------------
# Backtesting
# ---------------------------------------------------------------------------
class BacktestRequest(BaseModel):
    strategy: str = "all"  # UC1 | UC2 | DC1 | DC2 | UR1 | DR1 | UR2 | DR2 | all
    start_date: date | None = None
    end_date: date | None = None
    tickers: list[str] | None = None
    holding_days: int = 10


class BacktestMetrics(BaseModel):
    strategy: str
    trades: int
    win_rate: float
    avg_return_pct: float
    max_drawdown_pct: float
    profit_factor: float
    sharpe: float
    avg_holding_days: float
    start_date: date
    end_date: date


class BacktestResultOut(BaseModel):
    run_id: int | None = None
    strategies: list[BacktestMetrics]


# ---------------------------------------------------------------------------
# Paper trading (optional)
# ---------------------------------------------------------------------------
class PositionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticker: str
    side: str
    qty: float
    entry_price: float
    current_price: float | None = None
    status: str
    opened_at: datetime
    pnl: float | None = None


class OrderRequest(BaseModel):
    ticker: str
    side: str  # buy | put
    qty: float = 1.0


# ---------------------------------------------------------------------------
# LLM research agent
# ---------------------------------------------------------------------------
class ResearchRequest(BaseModel):
    """Optional narrowing of a research pass."""

    signal_ids: list[int] | None = None
    limit: int | None = Field(default=None, ge=1, le=100)
    force: bool = False  # re-annotate signals that already have an annotation


class ResearchStatusResponse(BaseModel):
    enabled: bool
    configured: bool
    model: str
    running: bool
    total_signals: int
    annotated_signals: int
    pending_signals: int
    max_confidence_delta: float
    max_signals_per_run: int
    sentiments: list[str]
    risk_flags: list[str]
    started_at: datetime | None = None
    finished_at: datetime | None = None
    last_result: dict | None = None
    error: str | None = None
