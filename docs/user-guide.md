# User Guide

## 1. Getting started

1. Launch the app and sign in with your credentials.
2. The home page is **SMC Analysis**. Visitors who are not signed in see a synthetic
   demo dataset; the real analysis is served to a signed-in user.

## 2. Connecting your Alpaca account

1. Open **Settings** from the navigation.
2. Under **Alpaca (market data & trading)**:
   - Paste your **API Key** and **Secret Key**.
   - Keep **Paper trading** checked to use Alpaca's paper endpoint (safe).
   - Click **Save Alpaca keys**, then **Test connection**.
3. A green "✓" confirms a valid connection. The stored key is shown only in
   masked form and can never be read back.

Optional providers — **Finnhub** (calendars), **FRED** (interest rates),
**Polygon** (alternative bars) — are added the same way.

## 3. Loading data — there is no scheduled download

Nothing fetches prices on a timer: no cron job, no background download. Data is
pulled **only when an administrator asks for it**.

1. Sign in as an admin.
2. Press **↻ Refresh** on the SMC Analysis page (or `POST /api/refresh`).
3. The refresh pulls daily bars for the universe, plus the hourly bars behind the
   4-hour refinement chart, and records when it finished.

Until you refresh, the analysis runs on whatever is already stored. If a symbol
has no stored candles it is skipped rather than guessed at.

## 4. SMC Analysis — reading the results

The page ranks the universe and shows one row per symbol that reached a verdict.
Each row carries the confidence score, the trend, whether a 1D break of structure
was confirmed, the 1-day Fair Value Gap zone, the entry, stop and take profit, and
the risk-to-reward.

| Column | Meaning |
|---|---|
| **Confidence** | 0–100. **0 means no trade**, always |
| **Trend** | The daily swing structure: Bullish, Bearish, or Neutral |
| **1D BOS** | Whether a definitive break of structure was confirmed |
| **1D FVG zone** | The gap the impulse left behind, or `n/a` |
| **Entry / Stop / Take profit** | The 4-hour refinement levels |
| **R:R** | Risk-to-reward. A trade requires **1:1.6 or better** |

A **No trade** label on a row is a real answer, not an error. The reason is always
stated. Setups rejected only on reward still show their levels, so you can see how
close they were.

### Step 1 — daily structure

The engine reads the daily swing sequence, calls the trend, then looks for a close
beyond a significant prior swing in that direction. That break is what makes the
setup directional.

### Step 2 — the gap, then the 4-hour refinement

The Fair Value Gap left by the impulse that broke structure is the only place a
trade can start. **If there is no valid, unmitigated gap, confidence is 0 and the
analysis stops.**

The 4-hour chart then refines it:

- **Entry** — the gap's 50% mean threshold.
- **Stop** — beyond the swing that created the gap, so it sits at a structural
  invalidation rather than the gap edge where a wick can reach it.
- **Take profit** — the next liquidity pool: the nearest swing beyond the entry.

## 5. Drill-down

Click any row. The detail panel shows:

- The **plain-text verdict** — the exact block with `Symbol`, `Confidence Score`,
  `Trend Direction`, `1D BOS Confirmed`, `1D FVG Zone`, `4H Refinement`, `Entry
  Price`, `Stop Loss`, `Take Profit`, `Risk Reward Ratio` and `Reasoning`.
- The **daily structure chart**, with the gap shaded and the entry, stop and
  target marked.
- **What the analysis saw** — the break of structure, the gap and the R:R, plus
  any blockers.

All candles are **closed**. A daily bar dated today is treated as still forming and
excluded, so a zone never appears and then disappears.

## 6. Macro dashboard

The **Macro** page shows the market regime (SPY vs its 200-day moving average),
VIX, the 10-year yield and Fed Funds rate, a sector relative-strength heatmap, the
economic calendar and upcoming earnings.

## 7. History

The **History** page lists previously stored signal rows with filters and
pagination, and the accuracy summary shows how past picks resolved.

## 8. Administration

| Task | Where |
|---|---|
| Refresh data | **↻ Refresh** on SMC Analysis |
| Alpaca / provider keys | **Settings** |
| Add or disable users, grant admin | **Users** |

> Educational and analytical output only. This is not financial advice.
