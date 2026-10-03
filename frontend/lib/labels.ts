// Human-readable vocabulary for everything the engine reports.
//
// The rules are written in full here rather than abbreviated in the UI: the
// backend emits short keys such as `bullish_exe_close_above_lp`, and this module
// renders them as "Bullish entry-execution candle closed at or above the
// liquidity point". Abbreviations (EXE, LP, SMA, ATR, RR, RSI) are always
// expanded in user-facing text.

export const CONTINUATION_FACTORS: Record<string, string> = {
  trend_separation:
    "How far price sits beyond the 50-period simple moving average, measured in Average True Range units",
  ma_alignment:
    "Separation between the 20-period and the 50-period simple moving averages",
  pullback_control: "How shallow and orderly the pullback was",
  structure_clean: "No aggressive counter-trend candle before the trigger",
  trigger_strength:
    "Entry-execution candle quality, how far it cleared the liquidity point, and how promptly it did so",
  volume_confirmation: "Traded volume compared with its 20-period average",
  volatility_expansion:
    "Entry-execution candle range compared with the Average True Range",
};

export const REVERSAL_FACTORS: Record<string, string> = {
  flush_intensity: "Size and aggression of the flush into the level",
  liquidity_sweep: "Whether a prior swing extreme was taken out",
  reversal_trigger:
    "Recovery candle quality and how far it reclaimed past the liquidity point",
  exhaustion:
    "Relative Strength Index stretch and how far price has run from its mean",
  structure:
    "Pattern quality: how closely a double top or double bottom matches, and how deep the retracement was",
};

export const GROUP_LABELS: Record<string, string> = {
  continuation: "Continuation factors",
  reversal: "Reversal factors",
};

export const RULE_LABELS: Record<string, string> = {
  positive_flow:
    "Price is trending above the 50-period simple moving average (positive flow)",
  negative_flow:
    "Price is trending below the 50-period simple moving average (negative flow)",
  sma20_above_sma50:
    "The 20-period simple moving average sits above the 50-period one",
  sma20_below_sma50:
    "The 20-period simple moving average sits below the 50-period one",
  shallow_pullback:
    "Shallow pullback that held beyond the 50-period simple moving average",
  deep_pullback_50sma:
    "Deeper pullback that tested the 50-period simple moving average",
  no_counter_flush:
    "No aggressive counter-trend candle in the run-up to the pullback",
  no_counter_flush_3_bars:
    "No counter-trend flush in the three candles before the reference point",
  bullish_exe_close_above_lp:
    "Bullish entry-execution candle closed at or above the liquidity point",
  bearish_exe_close_below_lp:
    "Bearish entry-execution candle closed at or below the liquidity point",
  sideways_range: "Price was moving sideways before the reversal",
  downside_flush: "A downside flush forced liquidity out of the market",
  liquidity_swept: "A prior swing extreme was swept",
  liqudity_swept: "A prior swing extreme was swept",
  lp_formed: "A liquidity point formed",
  liquidity_formed: "A liquidity point formed",
  bullish_exe: "A bullish entry-execution candle confirmed the turn",
  bearish_exe: "A bearish entry-execution candle confirmed the turn",
  close_at_or_above_lp: "Closed at or above the liquidity point",
  close_at_or_below_lp: "Closed at or below the liquidity point",
  majority_flush:
    "Majority flush: at least two flush candles within the last three",
  no_bar_count_required: "No bar-count limit applies to this setup",
  double_bottom: "A double bottom formed",
  double_top: "A double top formed",
  neckline_breakout: "The neckline broke to the upside",
  fails_at_lp: "Price failed at the liquidity point",
  bigger_retracement: "The retracement is deeper than the previous one",
  partial_overlap:
    "The two retracements overlap partially (neither one engulfs the other)",
};

const RULE_PATTERNS: Array<[RegExp, (match: RegExpMatchArray) => string]> = [
  [
    /^exe_within_(\d+)_bars$/,
    (m) =>
      `The entry-execution candle arrived within ${m[1]} candle${m[1] === "1" ? "" : "s"}`,
  ],
];

/** Render a backend rule key as a full sentence. */
export function ruleLabel(rule: string): string {
  if (RULE_LABELS[rule]) return RULE_LABELS[rule];
  for (const [pattern, build] of RULE_PATTERNS) {
    const match = rule.match(pattern);
    if (match) return build(match);
  }
  return rule.replace(/_/g, " ");
}

/** Render a risk-flag key as readable text. */
export function flagLabel(flag: string): string {
  return flag.replace(/_/g, " ");
}

export const CONFIDENCE_ADJUSTMENT_LABELS: Record<string, string> = {
  regime_adjustment: "Market regime alignment",
  sector_adjustment: "Sector rotation",
  counter_impact: "Counter impact — macro events and media arguing against the trade",
  confirmation_boost: "Volume and Average True Range confirmation",
};

export const OUTCOME_LABELS: Record<string, string> = {
  TARGET_HIT: "Target reached",
  STOP_HIT: "Stop reached",
  OPEN: "Still open",
  EXPIRED: "Expired unresolved",
};
