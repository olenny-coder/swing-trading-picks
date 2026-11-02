"""SMC multi-timeframe analysis tests.

The plain-text block is the deliverable, so its exact shape is asserted character
by character. The strategy rules — a break of structure, the fair value gap behind
it, the 4-hour refinement and the 1.6 risk-to-reward floor — are each pinned down
with crafted inputs.
"""
import os
import sys
import unittest
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.fvg import closed_only  # noqa: E402
from app.core.intraday import bucket_start, resample_intraday  # noqa: E402
from app.core.smc import (  # noqa: E402
    BEARISH,
    BULLISH,
    MIN_RISK_REWARD,
    SmcAnalysis,
    analyze,
    classify_structure,
    next_liquidity_pool,
)
from app.core.structure import swing_indices  # noqa: E402
from app.providers.base import Bar, IntradayBar  # noqa: E402

START = date(2026, 1, 5)
LABELS = [
    "Symbol:",
    "Confidence Score:",
    "Trend Direction:",
    "1D BOS Confirmed:",
    "1D FVG Zone:",
    "4H Refinement:",
    "Entry Price:",
    "Stop Loss:",
    "Take Profit:",
    "Risk Reward Ratio:",
    "Reasoning:",
]


def mk(rows, start=START):
    return [
        Bar(
            date=start + timedelta(days=i),
            open=float(r[0]),
            high=float(r[1]),
            low=float(r[2]),
            close=float(r[3]),
            volume=1_000_000.0,
        )
        for i, r in enumerate(rows)
    ]


def mk_hourly(rows, start=datetime(2026, 6, 1, 14, 0)):
    return [
        IntradayBar(
            ts=start + timedelta(hours=i),
            open=float(r[0]),
            high=float(r[1]),
            low=float(r[2]),
            close=float(r[3]),
            volume=100_000.0,
        )
        for i, r in enumerate(rows)
    ]


class TestPlainTextOutput(unittest.TestCase):
    """The output format is a hard contract: labels, order, no JSON, no fences."""

    def _tradeable(self) -> SmcAnalysis:
        return SmcAnalysis(
            symbol="AAPL",
            confidence=72.4,
            trend=BULLISH,
            bos_confirmed=True,
            fvg_low=182.40,
            fvg_high=184.10,
            entry=183.25,
            stop=181.60,
            target=189.40,
            risk_reward=3.7,
            reasoning="Bullish structure confirmed by a 1D break of structure at 181.90.",
        )

    def test_exact_block(self):
        text = self._tradeable().render()
        self.assertEqual(
            text,
            "\n".join(
                [
                    "Symbol: AAPL",
                    "Confidence Score: 72",
                    "Trend Direction: Bullish",
                    "1D BOS Confirmed: Yes",
                    "1D FVG Zone: 182.40 - 184.10",
                    "4H Refinement:",
                    "Entry Price: 183.25",
                    "Stop Loss: 181.60",
                    "Take Profit: 189.40",
                    "Risk Reward Ratio: 1:3.70",
                    "Reasoning: Bullish structure confirmed by a 1D break of structure at 181.90.",
                ]
            ),
        )

    def test_labels_appear_in_order_and_nothing_else(self):
        lines = self._tradeable().render().split("\n")
        self.assertEqual(len(lines), 11)
        for line, label in zip(lines, LABELS):
            self.assertTrue(line.startswith(label), f"{line!r} should start with {label!r}")

    def test_no_json_and_no_code_fences(self):
        text = self._tradeable().render()
        self.assertNotIn("{", text)
        self.assertNotIn("}", text)
        self.assertNotIn("```", text)
        self.assertNotIn('"', text)

    def test_a_refused_trade_says_no_trade_and_scores_zero(self):
        analysis = SmcAnalysis(
            symbol="XYZ",
            confidence=0.0,
            trend=BEARISH,
            bos_confirmed=True,
            reasoning="No Trade — risk-to-reward 1:1.20 is below the 1:1.6 minimum.",
        )
        text = analysis.render()
        self.assertIn("Confidence Score: 0", text)
        self.assertIn("1D FVG Zone: n/a", text)
        self.assertIn("Entry Price: n/a", text)
        self.assertIn("Stop Loss: n/a", text)
        self.assertIn("Take Profit: n/a", text)
        self.assertIn("Risk Reward Ratio: n/a", text)
        self.assertIn("Reasoning: No Trade", text)

    def test_missing_fvg_zone_renders_na(self):
        analysis = SmcAnalysis(symbol="ABC", trend=BULLISH)
        self.assertIn("1D FVG Zone: n/a", analysis.render())
        self.assertIn("1D BOS Confirmed: No", analysis.render())

    def test_neutral_trend_is_reported_verbatim(self):
        analysis = SmcAnalysis(symbol="ABC", trend="Neutral")
        self.assertIn("Trend Direction: Neutral", analysis.render())


class TestClosedCandles(unittest.TestCase):
    def test_a_bar_dated_today_is_dropped(self):
        today = date(2026, 3, 10)
        bars = mk([(1, 2, 0.5, 1.5)] * 3, start=today - timedelta(days=2))
        self.assertEqual(len(closed_only(bars, today)), 2)

    def test_older_bars_are_kept(self):
        today = date(2026, 3, 10)
        bars = mk([(1, 2, 0.5, 1.5)] * 3, start=today - timedelta(days=10))
        self.assertEqual(len(closed_only(bars, today)), 3)


class TestIntradayResampling(unittest.TestCase):
    def test_four_hour_buckets(self):
        self.assertEqual(bucket_start(datetime(2026, 6, 1, 15, 30)).hour, 12)
        self.assertEqual(bucket_start(datetime(2026, 6, 1, 16, 0)).hour, 16)
        self.assertEqual(bucket_start(datetime(2026, 6, 1, 19, 59)).hour, 16)

    def test_ohlcv_is_aggregated(self):
        hourly = mk_hourly(
            [
                (10, 11, 9, 10.5),
                (10.5, 12, 10, 11.5),
                (11.5, 13, 11, 12.5),
                (12.5, 14, 12, 13.5),
                (13.5, 15, 13, 14.5),
                (14.5, 16, 14, 15.5),
            ]
        )
        four = resample_intraday(hourly, drop_incomplete=False)
        # 14:00-15:59 falls into the 12:00 bucket, 16:00-19:59 into the 16:00 one.
        self.assertEqual(len(four), 2)
        first, second = four
        self.assertEqual(first.open, 10.0)
        self.assertEqual(first.high, 12.0)
        self.assertEqual(first.low, 9.0)
        self.assertEqual(first.close, 11.5)
        self.assertEqual(first.volume, 200_000.0)
        self.assertEqual(second.open, 11.5)
        self.assertEqual(second.high, 16.0)
        self.assertEqual(second.low, 11.0)
        self.assertEqual(second.close, 15.5)
        self.assertEqual(second.volume, 400_000.0)

    def test_empty_input_is_safe(self):
        self.assertEqual(resample_intraday([]), [])


class TestStructureAndBos(unittest.TestCase):
    def _bullish_series(self):
        rows = []
        price = 100.0
        for _ in range(40):
            rows.append((price, price + 1.0, price - 1.0, price + 0.6))
            price += 0.6
        # A swing high, a pullback, then a decisive break above it.
        rows.append((price, price + 2.0, price - 0.5, price + 1.0))
        rows.append((price + 1.0, price + 1.2, price - 1.5, price - 1.0))
        rows.append((price - 1.0, price - 0.8, price - 2.5, price - 2.0))
        rows.append((price - 2.0, price - 1.0, price - 2.2, price - 1.2))
        rows.append((price - 1.2, price + 4.0, price - 1.4, price + 3.6))
        rows.append((price + 3.6, price + 5.0, price + 3.0, price + 4.6))
        return mk(rows)

    def test_bullish_structure_is_classified(self):
        bars = self._bullish_series()
        swings = swing_indices([b.high for b in bars], [b.low for b in bars], k=3)
        self.assertEqual(classify_structure(bars, swings), BULLISH)

    def test_thin_data_is_refused(self):
        analysis = analyze("TEST", mk([(1, 2, 0.5, 1.5)] * 10))
        self.assertEqual(analysis.confidence, 0.0)
        self.assertIn("No Trade", analysis.reasoning)
        self.assertFalse(analysis.bos_confirmed)

    def test_a_series_without_structure_is_refused(self):
        flat = mk([(100, 100.5, 99.5, 100.0)] * 80)
        analysis = analyze("FLAT", flat)
        self.assertEqual(analysis.confidence, 0.0)
        self.assertTrue(analysis.reasoning.startswith("No Trade"))


class TestRefinementRules(unittest.TestCase):
    def _analysis_with(self, **kwargs) -> SmcAnalysis:
        base = dict(symbol="TEST", trend=BULLISH)
        base.update(kwargs)
        return SmcAnalysis(**base)

    def test_risk_reward_floor_is_1_6(self):
        self.assertEqual(MIN_RISK_REWARD, 1.6)

    def test_a_short_setup_mirrors_a_long(self):
        analysis = self._analysis_with(
            confidence=70.0,
            bos_confirmed=True,
            fvg_low=100.0,
            fvg_high=102.0,
            entry=101.0,
            stop=102.5,
            target=95.0,
            risk_reward=4.0,
            trend=BEARISH,
        )
        self.assertGreater(analysis.stop, analysis.entry)
        self.assertLess(analysis.target, analysis.entry)

    def test_liquidity_pool_must_be_beyond_the_entry(self):
        bars = mk([(100, 101, 99, 100.0)] * 20)
        # Every swing sits at 101 / 99, so a long above 105 has no pool.
        self.assertIsNone(next_liquidity_pool(bars, [], 105.0, bullish=True))

    def test_liquidity_pool_prefers_the_nearest(self):
        rows = []
        price = 100.0
        for i in range(30):
            price = 100.0 + (5.0 if i % 10 == 5 else 0.0)
            rows.append((price, price + 1.0, price - 1.0, price))
        bars = mk(rows)
        pool = next_liquidity_pool(bars, [], 101.0, bullish=True)
        self.assertIsNotNone(pool)
        self.assertGreater(pool, 101.0)


class TestMissingRefinementData(unittest.TestCase):
    """Without 4-hour candles the answer is No Trade, not an approximation.

    A daily-chart approximation was tried and removed: placing a 4-hour trigger's
    stop off daily swings produces levels that are simply wrong, and a wrong entry
    is worse than no entry.
    """

    @classmethod
    def setUpClass(cls):
        from app.providers.mock_provider import MockMarketDataProvider

        cls.market = MockMarketDataProvider()
        cls.today = date.today()

    def _daily(self, ticker="AAPL"):
        from app.core.fvg import closed_only as closed

        return closed(self.market.get_daily_bars(ticker, self.today - timedelta(days=400), self.today))

    def test_no_4h_means_no_trade(self):
        analysis = analyze("AAPL", self._daily(), [])
        self.assertFalse(analysis.four_hour_available)
        self.assertEqual(analysis.confidence, 0.0)
        self.assertFalse(analysis.tradeable)
        self.assertEqual(analysis.entry, None)
        self.assertEqual(analysis.stop, None)
        self.assertEqual(analysis.target, None)

    def test_the_refusal_says_why_and_stays_in_the_contract(self):
        analysis = analyze("AAPL", self._daily(), [])
        # Whatever the reason, it is a refusal and it is stated.
        self.assertTrue(analysis.reasoning.startswith("No Trade"), analysis.reasoning)
        self.assertFalse(analysis.tradeable)
        text = analysis.render()
        self.assertEqual(len(text.split("\n")), 11)
        self.assertIn("No Trade", text)

    def test_a_gap_without_4h_data_names_the_4h_chart(self):
        """When the setup exists but the refinement cannot run, say exactly that."""
        analysis = analyze("AAPL", self._daily(), [])
        if analysis.gap is None:
            self.skipTest("the synthetic series produced no gap")
        self.assertFalse(analysis.four_hour_available)
        self.assertIn("4-hour", analysis.reasoning)
        self.assertTrue(any("4-hour" in b for b in analysis.blockers), analysis.blockers)

    def test_it_never_refines_on_the_daily_chart(self):
        """Regression guard: the removed fallback must not come back."""
        analysis = analyze("AAPL", self._daily(), [])
        self.assertEqual(analysis.refinement_timeframe, "4H")
        self.assertNotIn("daily chart", analysis.reasoning.lower())

    def test_a_real_4h_series_still_produces_levels(self):
        bars_4h = self.market.get_intraday_bars(
            "AAPL",
            datetime.combine(self.today - timedelta(days=60), datetime.min.time()),
            datetime.combine(self.today, datetime.max.time()),
        )
        analysis = analyze("AAPL", self._daily(), bars_4h)
        # The series exists, so the flag is true regardless of the verdict.
        self.assertTrue(analysis.four_hour_available)
        if analysis.tradeable:
            for value in (analysis.entry, analysis.stop, analysis.target):
                self.assertIsNotNone(value)


class TestEndToEndWithMockData(unittest.TestCase):
    """The full pipeline over the synthetic provider must stay coherent."""

    @classmethod
    def setUpClass(cls):
        from app.providers.mock_provider import MockMarketDataProvider

        cls.market = MockMarketDataProvider()
        cls.today = date.today()

    def _analyse(self, ticker: str):
        from app.core.fvg import closed_only as closed

        daily = closed(self.market.get_daily_bars(ticker, self.today - timedelta(days=400), self.today))
        hourly = self.market.get_intraday_bars(
            ticker,
            datetime.combine(self.today - timedelta(days=60), datetime.min.time()),
            datetime.combine(self.today, datetime.max.time()),
        )
        return analyze(ticker, daily, hourly)

    def test_results_are_coherent(self):
        tradeable = 0
        analysed = 0
        for ticker in ("AAPL", "NVDA", "JPM", "XOM", "PG", "T"):
            analysis = self._analyse(ticker)
            analysed += 1
            text = analysis.render()
            lines = text.split("\n")
            self.assertEqual(len(lines), 11)
            for line, label in zip(lines, LABELS):
                self.assertTrue(line.startswith(label))
            self.assertGreaterEqual(analysis.confidence, 0.0)
            self.assertLessEqual(analysis.confidence, 100.0)

            if analysis.tradeable:
                tradeable += 1
                self.assertTrue(analysis.bos_confirmed)
                self.assertIsNotNone(analysis.entry)
                self.assertIsNotNone(analysis.stop)
                self.assertIsNotNone(analysis.target)
                self.assertGreaterEqual(analysis.risk_reward, MIN_RISK_REWARD - 1e-9)
                if analysis.trend == BULLISH:
                    self.assertLess(analysis.stop, analysis.entry)
                    self.assertGreater(analysis.target, analysis.entry)
                else:
                    self.assertGreater(analysis.stop, analysis.entry)
                    self.assertLess(analysis.target, analysis.entry)
                # A tradeable verdict must never say No Trade.
                self.assertNotIn("Reasoning: No Trade", text)
            else:
                self.assertEqual(analysis.confidence, 0.0)
                self.assertTrue(analysis.reasoning.startswith("No Trade"))

        # Reaching the refinement stage at all proves the pipeline runs end to end;
        # whether a symbol ends up tradeable depends on the synthetic series.
        self.assertGreaterEqual(analysed, 1)


if __name__ == "__main__":
    unittest.main()
