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

/** The live strategy first, then the retired SMA 20/50 flow-system setups. */
export type SetupCode =
  | "SMC"
  | "UC1" | "UC2" | "DC1" | "DC2" | "UR1" | "DR1" | "UR2" | "DR2";

export const SETUP_CODES: SetupCode[] = [
  "SMC",
  "UC1", "UC2", "DC1", "DC2", "UR1", "DR1", "UR2", "DR2",
];

export const SETUP_LABELS: Record<SetupCode, string> = {
  SMC: "SMC — 1D break of structure + fair value gap, 4H refinement",
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

/** One drawing instruction for the structure chart. */
export interface ChartAnnotation {
  kind: "fvg" | "level" | "zone" | "box" | "trendline" | "marker";
  label: string;
  color?: string;
  top?: number;
  bottom?: number;
  price?: number;
  from_date?: string;
  to_date?: string;
  date?: string;
  position?: "aboveBar" | "belowBar" | "inBar";
  shape?: "arrowUp" | "arrowDown" | "circle" | "square";
  style?: string;
  emphasis?: boolean;
  points?: { date: string; price: number }[];
}

// ---------------------------------------------------------------------------
// SMC multi-timeframe analysis (1D structure, 4H refinement)
// ---------------------------------------------------------------------------

/** Something scheduled that could invalidate a pick. */
export interface MacroFlag {
  kind: "macro" | "macro_next" | "earnings";
  title: string;
  when: string;
  importance: string;
  sentiment?: string;
  impact?: string;
}

export interface SmcResult {
  symbol: string;
  /** The plain-text block from the brief. This is the deliverable. */
  text: string;
  confidence: number;
  trend: "Bullish" | "Bearish" | "Neutral";
  bos_confirmed: boolean;
  fvg_low: number | null;
  fvg_high: number | null;
  entry: number | null;
  stop: number | null;
  target: number | null;
  risk_reward: number | null;
  reasoning: string;
  tradeable: boolean;
  triggered: boolean;
  four_hour_available: boolean;
  /** Which chart the levels were refined on: "4H" or "1D". */
  refinement_timeframe?: string;
  /** Scheduled events that could invalidate this pick. */
  macro_flags?: MacroFlag[];
  price: number | null;
  as_of: string | null;
  bos: Record<string, unknown> | null;
  gap: Record<string, unknown> | null;
  blockers: string[];
  reasons: string[];
}

export interface SmcScan {
  generated_at: string | null;
  scanned: number;
  analysed: number;
  tradeable: number;
  min_risk_reward: number;
  refinement_interval: string;
  intraday_available: boolean;
  results: SmcResult[];
  data_status?: {
    ready: boolean;
    daily_bars: number;
    daily_latest: string | null;
    refinement_bars: number | null;
    refinement_latest: string | null;
    message: string;
    market_day_note?: string;
  };
  demo: boolean;
}

export interface SmcSymbol extends SmcResult {
  name: string | null;
  sector: string | null;
  timeframe: string;
  daily_bars: BarOut[];
  refinement_bars: { time: string; open: number; high: number; low: number; close: number; volume: number }[];
  /** Live price context. Display only — the trade levels never move. */
  live?: {
    available: boolean;
    price?: number;
    change_pct?: number | null;
    prev_close?: number | null;
    session_high?: number | null;
    session_low?: number | null;
    as_of?: string | null;
    feed?: string;
    distance_pct?: number | null;
    in_zone?: boolean;
    status?: string;
  };
  demo: boolean;
}
