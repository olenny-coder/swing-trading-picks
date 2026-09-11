"""Deterministic MOCK data providers.

These let the entire application run end-to-end without any external API keys:
market data, options, macro/economic calendar, earnings calendar, and market
regime are all synthesized from a stable per-ticker random seed, so every run
produces the same series. This is both the demo mode and the test fixture.

The generators intentionally engineer a handful of "hero" tickers per signal
type so the daily view reliably shows BUY_STANDARD, BUY_DOJI_REVERSAL and SELL
signals out of the box.
"""
from __future__ import annotations

import random
from datetime import date, datetime, time, timedelta

from ..core.constants import SECTOR_ETFS
from ..core.universe import UNIVERSE
from .base import (
    Bar,
    EarningsData,
    MacroDataProvider,
    MacroEventData,
    MacroSnapshotData,
    MarketDataProvider,
    OptionContract,
    Quote,
    UniverseMeta,
)

HERO_DOJI_MOD = 2
HERO_BUY_MOD = 0
HERO_PUT_MOD = 7


def _trading_days(start: date, end: date) -> list[date]:
    out: list[date] = []
    d = start
    while d <= end:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def _rng(ticker: str) -> random.Random:
    return random.Random(f"stp::{ticker}")


def _base_price(ticker: str) -> float:
    return 10.0 + (sum(ord(c) for c in ticker) % 400) * 0.6


def _hero_type(ticker: str) -> int:
    return sum(ord(c) for c in ticker) % 10


# ---------------------------------------------------------------------------
# Bar series generation
# ---------------------------------------------------------------------------
def _generate_bars(ticker: str, start: date, end: date) -> list[Bar]:
    rng = _rng(ticker)
    days = _trading_days(start, end)
    n = len(days)
    if n == 0:
        return []

    price = _base_price(ticker)
    drift = rng.uniform(-0.0008, 0.0008)
    vol = rng.uniform(0.015, 0.030)
    base_volume = rng.uniform(500_000, 5_000_000)

    closes: list[float] = []
    regime_drift = drift
    regime_left = 0
    for _ in range(n):
        if regime_left <= 0:
            regime_left = rng.randint(15, 45)
            regime_drift = rng.uniform(-0.006, 0.006)
        regime_left -= 1
        ret = regime_drift + rng.gauss(0, vol)
        price = max(price * (1.0 + ret), 1.0)
        closes.append(price)

    bars: list[Bar] = []
    for i, d in enumerate(days):
        c = closes[i]
        prev_c = closes[i - 1] if i else c
        o = prev_c * (1.0 + rng.gauss(0, vol / 3.0))
        ret = (c - prev_c) / prev_c if prev_c else 0.0
        intraday = abs(c - o) + c * vol * rng.uniform(0.2, 0.9)
        h = max(o, c) + intraday * rng.uniform(0.1, 0.5)
        low = min(o, c) - intraday * rng.uniform(0.1, 0.5)
        v = base_volume * rng.uniform(0.6, 1.6) * (1.0 + abs(ret) / (2.0 * vol))
        bars.append(Bar(date=d, open=round(o, 2), high=round(h, 2), low=round(low, 2), close=round(c, 2), volume=v))

    _craft_tail(ticker, bars, rng)
    return bars


def _craft_tail(ticker: str, bars: list[Bar], rng: random.Random) -> None:
    """Engineer the final bars of 'hero' tickers into clean signal patterns."""
    hero = _hero_type(ticker)
    if hero == HERO_BUY_MOD:
        _craft_buy(bars)
    elif hero == HERO_PUT_MOD:
        _craft_put(bars)
    elif hero == HERO_DOJI_MOD:
        _craft_doji(bars, rng)


def _rewrite_ohlc(bar: Bar, o: float, c: float, h: float, l: float, v: float | None = None) -> None:
    bar.open = round(o, 2)
    bar.close = round(c, 2)
    bar.high = round(h, 2)
    bar.low = round(l, 2)
    if v is not None:
        bar.volume = v


def _avg_volume(bars: list[Bar], window: int = 20) -> float:
    if not bars:
        return 1_000_000.0
    window_bars = bars[-window:]
    return sum(b.volume for b in window_bars) / len(window_bars)


def _craft_buy(bars: list[Bar]) -> None:
    """Engineer a BUY_STANDARD setup: steady uptrend -> drifting consolidation
    (pulls MACD below signal, resets RSI) -> multi-bar breakout above the
    20-day high with a volume spike on the final bar."""
    n = len(bars)
    if n < 60:
        return
    anchor = bars[n - 60].close
    closes: list[float] = []
    for k in range(42):  # steady uptrend (establishes EMA20 > EMA50)
        closes.append(anchor * (1.0 + 0.0032 * (k + 1)))
    peak = closes[-1]
    for k in range(14):  # drifting consolidation
        drift = peak * (1.0 - 0.0028 * (k + 1))
        sign = 1 if k % 2 == 0 else -1
        closes.append(drift * (1.0 + sign * 0.0035))
    base = closes[-1]
    for k in range(4):  # breakout
        closes.append(base * (1.0 + 0.017 * (k + 1)))
    for idx, c in enumerate(closes):
        i = n - 60 + idx
        _rewrite_ohlc(bars[i], c * 0.998, c, c * 1.012, c * 0.988)
    bars[-1].volume = _avg_volume(bars) * 2.2


def _craft_put(bars: list[Bar]) -> None:
    """Mirror of buy: steady downtrend -> drifting consolidation (pushes MACD
    above signal) -> multi-bar breakdown below the 20-day low."""
    n = len(bars)
    if n < 60:
        return
    anchor = bars[n - 60].close
    closes: list[float] = []
    for k in range(42):  # steady downtrend
        closes.append(anchor * (1.0 - 0.0032 * (k + 1)))
    trough = closes[-1]
    for k in range(14):  # drifting consolidation (bounce resets RSI upward)
        drift = trough * (1.0 + 0.004 * (k + 1))
        sign = 1 if k % 2 == 0 else -1
        closes.append(drift * (1.0 + sign * 0.003))
    base = closes[-1]
    for k in range(4):  # breakdown
        closes.append(base * (1.0 - 0.017 * (k + 1)))
    for idx, c in enumerate(closes):
        i = n - 60 + idx
        _rewrite_ohlc(bars[i], c * 1.002, c, c * 1.012, c * 0.988)
    bars[-1].volume = _avg_volume(bars) * 2.2


def _craft_doji(bars: list[Bar], rng: random.Random) -> None:
    """Downtrend -> doji -> bullish confirmation day (dips below doji low,
    closes above it in the upper half of the range on above-average volume)."""
    n = len(bars)
    if n < 30:
        return
    anchor = bars[n - 30].close
    # Downtrend
    for i in range(n - 29, n - 2):
        c = anchor * (1.0 - 0.006 * (i - (n - 29)))
        _rewrite_ohlc(bars[i], c * 1.002, c, c * 1.01, c * 0.99)

    # Doji candle (second to last)
    doji_close = bars[n - 3].close
    doji_range = doji_close * 0.03
    doji_low = doji_close - doji_range / 2
    doji_high = doji_close + doji_range / 2
    doji_open = doji_close * 1.001  # tiny body (<=10% of range)
    _rewrite_ohlc(bars[n - 2], doji_open, doji_close, doji_high, doji_low)

    # Confirmation candle (last): dips below doji low, closes near the high
    # (upper half) and above the doji low.
    conf_low = doji_low * 0.997
    conf_close = doji_low * 1.02
    conf_high = conf_close * 1.01
    conf_open = doji_close * 0.998
    _rewrite_ohlc(bars[n - 1], conf_open, conf_close, conf_high, conf_low)
    bars[-1].volume = _avg_volume(bars) * 1.6


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------
class MockMarketDataProvider(MarketDataProvider):
    name = "mock"

    def test_connection(self) -> tuple[bool, str, dict | None]:
        return True, "Mock provider is ready (no external keys required).", {"mode": "mock"}

    def get_universe(self, min_price: float = 5.0, min_volume: float = 500_000.0) -> list[UniverseMeta]:
        out: list[UniverseMeta] = []
        for ticker, name, sector in UNIVERSE:
            price = _base_price(ticker)
            vol = 500_000 + (sum(ord(c) for c in ticker) % 500) * 12_000
            if price >= min_price and vol >= min_volume:
                out.append(UniverseMeta(ticker=ticker, name=name, sector=sector, price=price, avg_volume=vol))
        return out

    def get_daily_bars(self, ticker: str, start: date, end: date) -> list[Bar]:
        return _generate_bars(ticker, start, end)

    def get_quote(self, ticker: str) -> Quote:
        end = date.today()
        bars = _generate_bars(ticker, end - timedelta(days=30), end)
        if not bars:
            return Quote(ticker=ticker, price=_base_price(ticker))
        last = bars[-1]
        spread = max(last.close * 0.0005, 0.01)
        return Quote(
            ticker=ticker,
            price=last.close,
            volume=last.volume,
            bid=round(last.close - spread / 2, 2),
            ask=round(last.close + spread / 2, 2),
        )

    def get_options_chain(self, ticker: str, side: str = "put") -> list[OptionContract]:
        rng = _rng(f"opt::{ticker}")
        quote = self.get_quote(ticker)
        contracts: list[OptionContract] = []
        for i in range(12):
            strike_pct = 1.0 - (i + 1) * 0.03 if side == "put" else 1.0 + (i + 1) * 0.03
            strike = round(quote.price * strike_pct, 2)
            mid = max(quote.price * 0.02 * rng.uniform(0.3, 1.5), 0.05)
            spread = mid * rng.uniform(0.02, 0.08)
            oi = rng.choice([40, 80, 120, 250, 500, 1200, 3000])
            contracts.append(
                OptionContract(
                    symbol=f"{ticker}{date.today().strftime('%y%m%d')}{side[0].upper()}{strike}",
                    strike=strike,
                    type=side,
                    expiry=date.today() + timedelta(days=rng.randint(7, 60)),
                    bid=round(max(mid - spread / 2, 0.01), 2),
                    ask=round(mid + spread / 2, 2),
                    last=round(mid, 2),
                    open_interest=oi,
                    implied_volatility=round(rng.uniform(0.2, 0.7), 3),
                )
            )
        return contracts


class MockMacroProvider(MacroDataProvider):
    name = "mock"

    def __init__(self, now: date | None = None) -> None:
        self.now = now or date.today()

    def get_economic_calendar(self, start: date, end: date) -> list[MacroEventData]:
        events: list[MacroEventData] = []
        d = start
        while d <= end:
            if d.weekday() < 5:
                day = d.day
                if day == 1 and d.weekday() == 4:  # first Friday = NFP
                    events.append(self._ev("Non-Farm Payrolls", d, "high", "positive", "Employment", "180K", "175K"))
                elif day == 12:
                    events.append(self._ev("CPI (YoY)", d, "high", "positive", "Inflation", "3.2%", "3.4%"))
                elif day == 14:
                    events.append(self._ev("PPI (MoM)", d, "medium", "positive", "Inflation", "0.2%", "0.3%"))
                elif (d - date(2024, 1, 1)).days % 42 == 0:
                    events.append(self._ev("FOMC Rate Decision", d, "high", "neutral", "Interest Rates", "5.25%", "5.25%"))
                elif (d - date(2024, 1, 3)).days % 90 == 0:
                    events.append(self._ev("GDP (QoQ)", d, "high", "negative", "GDP", "2.1%", "2.4%"))
                elif day == 20:
                    events.append(self._ev("Existing Home Sales", d, "low", "negative", "Housing", "4.0M", "4.1M"))
            d += timedelta(days=1)
        return events

    @staticmethod
    def _ev(
        title: str, d: date, importance: str, sentiment: str, category: str, forecast: str, previous: str
    ) -> MacroEventData:
        return MacroEventData(
            title=title,
            datetime=datetime.combine(d, time(8, 30)),
            importance=importance,
            sentiment=sentiment,
            category=category,
            forecast=forecast,
            previous=previous,
            source="mock",
        )

    def get_earnings_calendar(self, tickers: list[str], start: date, end: date) -> list[EarningsData]:
        out: list[EarningsData] = []
        span = max((end - start).days, 1)
        for i, ticker in enumerate(tickers):
            rng = _rng(f"ern::{ticker}")
            # Scatter earnings across the window; ~12% land within 7 days of "now".
            if i % 8 == 0:
                offset = rng.randint(1, 6)
            else:
                offset = rng.randint(7, span - 1) if span > 7 else rng.randint(1, 6)
            report = self.now + timedelta(days=offset)
            if start <= report <= end:
                out.append(
                    EarningsData(
                        ticker=ticker,
                        report_date=report,
                        fiscal_quarter=f"Q{(report.month - 1) // 3 + 1} {report.year}",
                        eps_estimate=round(rng.uniform(0.3, 5.0), 2),
                        eps_actual=round(rng.uniform(0.2, 5.2), 2),
                        revenue_estimate=round(rng.uniform(500, 80_000), 0),
                        source="mock",
                    )
                )
        return out

    def get_macro_snapshot(self) -> MacroSnapshotData:
        rng = _rng("macro")
        spy_close = round(rng.uniform(500, 620), 2)
        spy_ma200 = round(spy_close * rng.uniform(0.92, 1.06), 2)
        regime = "bullish" if spy_close > spy_ma200 else "bearish"
        vix = round(rng.uniform(12, 28), 2)
        if vix > 24:
            regime = "bearish"
        strength: dict[str, float] = {}
        for etf in SECTOR_ETFS:
            strength[etf] = round(rng.uniform(-8.0, 12.0), 2)
        return MacroSnapshotData(
            date=self.now,
            regime=regime,
            spy_close=spy_close,
            spy_ma200=spy_ma200,
            vix=vix,
            vix_term_structure=round(rng.uniform(-3.0, 3.0), 2),
            ten_year_yield=round(rng.uniform(3.8, 4.8), 2),
            fed_funds_rate=round(rng.uniform(5.0, 5.5), 2),
            sector_relative_strength=strength,
        )
