// Shared types mirroring the backend Pydantic schemas.

export type SignalType = "BUY_STANDARD" | "BUY_DOJI_REVERSAL" | "PUT";

export interface SignalOut {
  id: number;
  ticker: string;
  name: string | null;
  date: string;
  type: SignalType;
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
  total_puts: number;
  total_doji: number;
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
