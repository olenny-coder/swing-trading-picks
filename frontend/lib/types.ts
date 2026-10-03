// Shared types mirroring the backend Pydantic schemas.

export type SignalType = "BUY" | "SELL";

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
  entry: number;
  target: number;
  stop: number;
  confidence: number;
  price: number;
  sector: string | null;
  confidence_components: Record<string, number> | null;
  triggered_rules: string[] | null;
  event_flags: Record<string, unknown> | null;
  option_recommendation: OptionRecommendation | null;
  /** LLM research-agent output; null until the agent has annotated this signal. */
  annotation: SignalAnnotation | null;
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

export interface OptionRecommendation {
  symbol: string;
  strike: number;
  expiry: string | null;
  bid: number | null;
  ask: number | null;
  premium: number;
  open_interest: number | null;
  implied_volatility: number | null;
  option_entry: number;
  option_target: number;
  option_stop: number;
  underlying_entry: number;
  underlying_target: number;
  underlying_stop: number;
  liquid: boolean;
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

export interface OptionContractOut {
  symbol: string;
  strike: number;
  expiry: string | null;
  bid: number | null;
  ask: number | null;
  last: number | null;
  open_interest: number | null;
  implied_volatility: number | null;
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
  option_chain: OptionContractOut[];
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

export interface CredentialOut {
  provider: string;
  has_key: boolean;
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
