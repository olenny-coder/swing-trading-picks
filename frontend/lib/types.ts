// Shared types mirroring the backend Pydantic schemas.

export type SignalType = "BUY" | "SELL";

/** Candle interval the setup was read on. */
export type Timeframe = "DAILY" | "WEEKLY" | "MONTHLY";

export const TIMEFRAMES: Timeframe[] = ["DAILY", "WEEKLY", "MONTHLY"];

export const TIMEFRAME_LABELS: Record<Timeframe, string> = {
  DAILY: "Daily",
  WEEKLY: "Weekly",
  MONTHLY: "Monthly",
};

export const TIMEFRAME_DESCRIPTIONS: Record<Timeframe, string> = {
  DAILY:
    "Analysed on daily candles — the fastest reads, and the noisiest. A pulled-back trend can resume within a week.",
  WEEKLY:
    "Analysed on weekly candles — fewer setups, and the more durable ones. The same rules, read on a slower clock.",
  MONTHLY:
    "Analysed on monthly candles — position-trading context. Needs several years of price history before setups can form.",
};

/** Retrospective result of a pick. */
export type OutcomeStatus = "TARGET_HIT" | "STOP_HIT" | "OPEN" | "EXPIRED";

export interface SignalOutcome {
  status: OutcomeStatus;
  exit_price: number | null;
  exit_date: string | null;
  bars_held: number;
  pnl_pct: number;
  max_favourable_pct: number;
  max_adverse_pct: number;
  evaluated_at: string;
}

export interface SetupAccuracy {
  setup: string;
  total: number;
  TARGET_HIT: number;
  STOP_HIT: number;
  win_rate_pct: number | null;
}

export interface AccuracyResponse {
  timeframe: string | null;
  evaluated: number;
  target_hit: number;
  stop_hit: number;
  open: number;
  expired: number;
  decided: number;
  win_rate_pct: number | null;
  avg_pnl_pct: number | null;
  avg_win_pct: number | null;
  avg_loss_pct: number | null;
  by_setup: SetupAccuracy[];
}

/** SMA 20/50 flow-system setups. */
export type SetupCode = "UC1" | "UC2" | "DC1" | "DC2" | "UR1" | "DR1" | "UR2" | "DR2";

export const SETUP_CODES: SetupCode[] = ["UC1", "UC2", "DC1", "DC2", "UR1", "DR1", "UR2", "DR2"];

export const SETUP_LABELS: Record<SetupCode, string> = {
  UC1: "Bullish continuation (shallow pullback)",
  UC2: "Bullish continuation (deep pullback)",
  DC1: "Bearish continuation (shallow pullback)",
  DC2: "Bearish continuation (deep pullback)",
  UR1: "Early upside reversal",
  DR1: "Early downside reversal",
  UR2: "Double-top reversal",
  DR2: "Double-bottom reversal",
};

export interface SignalOut {
  id: number;
  ticker: string;
  name: string | null;
  date: string;
  type: SignalType;
  setup: SetupCode;
  timeframe: Timeframe;
  entry: number;
  target: number;
  stop: number;
  confidence: number;
  price: number;
  sector: string | null;
  confidence_components: Record<string, number> | null;
  triggered_rules: string[] | null;
  event_flags: Record<string, unknown> | null;
  /** LLM research-agent output; null until the agent has annotated this signal. */
  annotation: SignalAnnotation | null;
  /** Retrospective result once the pick has resolved. */
  outcome: SignalOutcome | null;
}

export type Sentiment = "bullish" | "bearish" | "neutral" | "mixed";

export interface SignalAnnotation {
  sentiment: Sentiment;
  risk_flags: string[];
  confidence_delta: number;
  /** How much adverse macro/media coverage argues against the trade (0-15). */
  counter_impact?: number;
  base_confidence: number;
  adjusted_confidence: number;
  supports_setup: boolean;
  rationale: string;
  model?: string;
  created_at?: string;
}

export interface ResearchStatus {
  enabled: boolean;
  configured: boolean;
  model: string;
  running: boolean;
  total_signals: number;
  annotated_signals: number;
  pending_signals: number;
  max_confidence_delta: number;
  max_signals_per_run: number;
  sentiments: string[];
  risk_flags: string[];
  started_at: string | null;
  finished_at: string | null;
  last_result: Record<string, unknown> | null;
  error: string | null;
}

export interface Summary {
  total_buys: number;
  total_sells: number;
  total_continuation: number;
  total_reversal: number;
  setup_counts: Record<string, number>;
  avg_confidence: number;
  high_confidence_count: number;
  regime: string | null;
  vix: number | null;
  upcoming_macro_events: number;
  earnings_risk_count: number;
  generated_at: string | null;
}

export interface SignalListResponse {
  signals: SignalOut[];
  total: number;
  limit: number;
  offset: number;
  summary: Record<string, unknown> | null;
  /** True when this is the synthetic demo dataset (visitor not signed in). */
  demo?: boolean;
}

export interface BarOut {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface SignalDetail {
  signal: SignalOut;
  bars: BarOut[];
  indicators: {
    ema20: (number | null)[];
    ema50: (number | null)[];
    rsi: (number | null)[];
    atr: (number | null)[];
    macd: (number | null)[];
    macd_signal: (number | null)[];
  };
  doji_highlight: boolean;
  /** True when this is the synthetic demo dataset (visitor not signed in). */
  demo?: boolean;
}

export interface MacroEventOut {
  id: number;
  title: string;
  datetime: string;
  importance: "high" | "medium" | "low";
  sentiment: "positive" | "negative" | "neutral";
  category: string | null;
  country: string;
  forecast: string | null;
  previous: string | null;
  actual: string | null;
}

export interface EarningsEventOut {
  id: number;
  ticker: string;
  report_date: string;
  fiscal_quarter: string | null;
  eps_estimate: number | null;
  eps_actual: number | null;
  revenue_estimate: number | null;
}

export interface MacroSnapshotOut {
  date: string;
  regime: string;
  spy_close: number | null;
  spy_ma200: number | null;
  vix: number | null;
  vix_term_structure: number | null;
  ten_year_yield: number | null;
  fed_funds_rate: number | null;
  sector_relative_strength: Record<string, number> | null;
}

export interface MacroDashboard {
  snapshot: MacroSnapshotOut | null;
  macro_events: MacroEventOut[];
  earnings: EarningsEventOut[];
  sector_heatmap: Record<string, number>;
  /** True when this is the synthetic demo dataset (visitor not signed in). */
  demo?: boolean;
}

/** An account that can sign in. Admins manage users; members just read live data. */
export interface UserOut {
  id: number;
  username: string;
  is_admin: boolean;
  is_active: boolean;
  created_at?: string | null;
}

export interface CredentialOut {
  provider: string;  has_key: boolean;
  key_masked: string | null;
  secret_masked: string | null;
  is_paper: boolean | null;
  updated_at: string | null;
}

export interface ProviderStatus {
  provider: string;
  configured: boolean;
  source: string;
}

export interface SettingsResponse {
  alpaca: CredentialOut | null;
  providers: ProviderStatus[];
  data_provider: string;
  environment_variables_present: boolean;
}

export interface TestConnectionResult {
  provider: string;
  ok: boolean;
  message: string;
  detail: Record<string, unknown> | null;
}

// ---------------------------------------------------------------------------
// Fair Value Gap + breakout-structure screener
// ---------------------------------------------------------------------------

/** One drawing instruction for the drill-down chart. */
export interface FvgAnnotation {
  kind: "fvg" | "level" | "zone" | "box" | "trendline" | "marker";
  label: string;
  color?: string;
  top?: number;
  bottom?: number;
  midpoint?: number;
  price?: number;
  from_date?: string;
  to_date?: string;
  date?: string;
  position?: "aboveBar" | "belowBar" | "inBar";
  shape?: "arrowUp" | "arrowDown" | "circle" | "square";
  style?: string;
  emphasis?: boolean;
  timeframe?: string;
  points?: { date: string; price: number }[];
}

export interface FvgSignalCard {
  ticker: string;
  timeframe: string;
  signal: string;
  direction: string | null;
  setup_type: string;
  confidence: number;
  entry: number | null;
  entry_zone: (number | null)[];
  stop: number | null;
  target1: number | null;
  target2: number | null;
  rr1: number | null;
  rr2: number | null;
  risk_per_share: number | null;
  risk_per_trade_pct: number;
  reasons: string[];
  blockers: string[];
  invalidation: string;
  no_trade: boolean;
  waiting: boolean;
  disclaimer: string;
}

export interface FvgRow {
  ticker: string;
  name: string | null;
  sector: string | null;
  timeframe: string;
  direction: string | null;
  status: string;
  setup_type: string;
  breakout_level: number | null;
  breakout_kind: string | null;
  breakout_date: string | null;
  fvg_top: number | null;
  fvg_bottom: number | null;
  fvg_midpoint: number | null;
  fvg_date: string | null;
  fvg_mitigation: number | null;
  entry: number | null;
  entry_low: number | null;
  entry_high: number | null;
  stop: number | null;
  target1: number | null;
  target2: number | null;
  rr1: number | null;
  rr2: number | null;
  confidence: number;
  price: number | null;
  atr: number | null;
  why: string;
  reasons: string[];
  blockers: string[];
  invalidation: string;
}

export interface FvgSettings {
  min_rr: number;
  risk_per_trade_pct: number;
  earnings_buffer_days: number;
  min_price: number;
  min_volume: number;
  min_market_cap: number;
  market_cap_applied: boolean;
  market_cap_note: string | null;
  allow_earnings_plays: boolean;
}

export interface FvgShortlist {
  timeframe: string;
  generated_at: string | null;
  screened: number;
  matched: number;
  max_watchlist: number;
  rows: FvgRow[];
  settings: FvgSettings;
  timeframes_available: string[];
  intraday: { available: boolean; intervals?: string[]; note?: string };
  method: string;
  demo: boolean;
}

export interface FvgDrilldown {
  ticker: string;
  name: string | null;
  sector: string | null;
  timeframe: string;
  as_of: string | null;
  signal_card: FvgSignalCard;
  annotations: FvgAnnotation[];
  chart_markup: Record<string, unknown>;
  structures: Record<string, unknown>[];
  fvg_gaps: Record<string, unknown>[];
  open_gap_count: number;
  bars: BarOut[];
  indicators: {
    ema20: (number | null)[];
    ema50: (number | null)[];
    atr: (number | null)[];
  };
  timeframes_available: string[];
  intraday: { available: boolean; intervals?: string[]; note?: string };
  demo: boolean;
}
