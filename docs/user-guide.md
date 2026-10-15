# User Guide

## 1. Getting started

1. Launch the app (see the README Quickstart) and sign in with your credentials.
2. The **Daily View** is the home screen. In demo mode it is pre-populated with
   sample signals so you can explore immediately.

## 2. Connecting your Alpaca account

1. Open **Settings** from the top navigation.
2. Under **Alpaca (market data & trading)**:
   - Paste your **API Key** and **Secret Key**.
   - Keep **Paper trading** checked to use Alpaca's paper endpoint (safe).
   - Click **Save Alpaca keys**, then **Test connection**.
3. A green "✓" confirms a valid connection. The stored key is shown only in
   masked form (e.g. `AK************1234`) and can never be read back.
4. To switch between paper and live, uncheck the box and save again.

You can also add optional providers (**Finnhub** for economic/earnings
calendars, **FRED** for interest rates, **Polygon** for alternative data) the
same way. Without them the app uses built-in simulated calendars so every
feature still works.

## 3. Reading the Daily View

- **Summary cards** show total buys, total sells, continuation and reversal
  counts, average confidence, the current market regime, VIX, and counts of
  upcoming macro events and earnings risks.
- The **interval selector** above the cards switches between **daily**, **weekly**
  and **monthly** candles. These are the same rules read on a different candle
  series, so each interval has its own list.
- The **Top 20 / All** toggle switches between the diversity-capped shortlist
  and the full signal list.
- Use **Filters** to narrow by direction, setup, sector, confidence and price,
  and to exclude earnings-week or macro-risk names.

### Signal types

| Badge | Meaning | When to use |
|---|---|---|
| `BUY` | Bullish setup | A trend resuming upward, or a completed downside reversal |
| `SELL` | Bearish setup | A downtrend resuming downward, or a completed upside reversal |

Levels are quoted on the **underlying itself**. The app reads stock prices only —
there is no options leg, so a `SELL` is expressed by selling the instrument
rather than by buying a put.

Each signal also carries one of eight setups: `UC1`/`UC2` and `DC1`/`DC2` for
continuation, `UR1`/`DR1` for early reversal, and `UR2`/`DR2` for double
top/bottom reversals.

Index futures such as **MES** (Micro E-mini S&P 500) appear in the same list when
their price history is available, marked with the *Index Futures* sector.

### Columns

- **Entry** — the price level the setup triggers at, with the last close beneath
  it for reference.
- **Target / Stop** — profit target and stop-loss levels, projected from the
  structural stop and the setup's risk-to-reward ratio.
- **Confidence** — 0–100 with a Low/Medium/High label.
- **Events** — `ERN nd` (earnings within *n* days) and `MACRO` (high-impact
  event near) flags.

## 4. Signal detail & charts

Click any signal (or the *Chart* link) to open its detail page, which shows:

- Entry, target and stop, plus the **result** once the pick has resolved.
- An interactive candlestick chart drawn on the **pick's own interval**, with
  **EMA 20/50** overlays and a **doji highlight**.
- The **triggered rules**, written out in full.
- The **confidence breakdown** showing the continuation and reversal factor
  scores, the blend weights, and every context adjustment.
- The **counter impact** — what macro events and media argue against the trade.
- The **event context** (regime, VIX, earnings proximity, sector rotation).

## 5. FVG Screener

A second, separate workflow, and it runs in **two deliberate steps**.

**Step 1 — the shortlist.** The page screens the universe and returns a ranked
table: ticker, direction, setup type, breakout level, FVG zone, entry zone, stop,
two targets, reward-to-risk, confidence and the reason. Nothing is charted yet.

The screen looks for a **confirmed breakout structure** (break of structure,
change of character, range breakout, flag breakout, trendline break, or a
supply/demand flip) and then for the **Fair Value Gap** that leg left behind. Only
instrument with both are listed. A `WAIT` row means the setup is valid but price
has not yet retraced into the gap; `NO TRADE` means a gate failed, and the reason
is shown.

**Step 2 — the drill-down.** Click any row. Only then does the app fetch and draw:

- the annotated chart — Fair Value Gap bands, the breakout level or trendline, the
  consolidation box, the entry band, entry marker, stop and both targets;
- the **signal card** — `BUY` / `SELL` / `WAIT` / `NO TRADE` with exact levels,
  risk per share, the reasons, the blockers and the invalidation condition;
- the **chart markup** as portable JSON.

Use **↻ Re-screen** to bypass the short-lived cache, and **Close drill-down** to
return to the list.

All candles are **closed** — a daily bar dated today is treated as still forming
and excluded — so a zone never appears and then disappears. If nothing qualifies,
the page says so rather than inventing a setup.

> Educational and analytical output only. This is not financial advice.

## 6. Macro dashboard

The **Macro** page shows the market regime (SPY vs its 200-day moving average),
VIX, the 10-year yield and Fed Funds rate, a **sector relative-strength
heatmap**, the **economic calendar**, and the **upcoming earnings** list. These
feed directly into signal selection and confidence.

## 7. History

The **History** page lists all signals across dates with the same filters plus
pagination.

## 7. Alerts (high-confidence signals)

High-confidence signals (≥ 71) that pass all filters are surfaced at the top of
the Daily View. For external notifications, wire the `high_confidence_count`
field of the summary into your alerting tool of choice.
