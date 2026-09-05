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

- **Summary cards** show total buys, doji reversals, puts, average confidence,
  the current market regime, VIX, and counts of upcoming macro events and
  earnings risks.
- The **Top 20 / All** toggle switches between the diversity-capped shortlist
  and the full signal list.
- Use **Filters** to narrow by signal type, sector, confidence, price, and to
  exclude earnings-week or macro-risk names.

### Signal types

| Badge | Meaning | When to use |
|---|---|---|
| `BUY` | Momentum breakout | Trending stocks breaking to new highs |
| `DOJI` | Doji reversal | A downtrend that prints a doji and confirms bullish the next day |
| `PUT` | Bearish setup | Buying a put option on a breakdown (no shorting) |

### Columns

- **Entry / Option** — for `PUT`, the recommended put premium and strike; for
  buys, the entry price.
- **Target / Stop** — profit target and stop-loss levels.
- **Confidence** — 0–100 with a Low/Medium/High label.
- **Events** — `ERN nd` (earnings within *n* days) and `MACRO` (high-impact
  event near) flags.

## 4. Signal detail & charts

Click any signal (or the *Chart* link) to open its detail page, which shows:

- Entry / target / stop (and the full put-option recommendation for `PUT`).
- An interactive candlestick chart with **EMA 20/50** overlays and a **doji
  highlight**.
- The **triggered rules** and the **confidence breakdown** (six sub-scores).
- The **event context** (regime, VIX, earnings proximity, sector rotation).

## 5. Macro dashboard

The **Macro** page shows the market regime (SPY vs its 200-day moving average),
VIX, the 10-year yield and Fed Funds rate, a **sector relative-strength
heatmap**, the **economic calendar**, and the **upcoming earnings** list. These
feed directly into signal selection and confidence.

## 6. History

The **History** page lists all signals across dates with the same filters plus
pagination.

## 7. Alerts (high-confidence signals)

High-confidence signals (≥ 71) that pass all filters are surfaced at the top of
the Daily View. For external notifications, wire the `high_confidence_count`
field of the summary into your alerting tool of choice.
