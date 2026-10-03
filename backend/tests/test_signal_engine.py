"""Unit tests for the SMA 20/50 flow-based setup engine.

Uses synthetic daily series so each setup is deterministic.
"""
import math
import os
import sys
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.base_types import SignalContext  # noqa: E402
from app.core.constants import SIGNAL_BUY, SIGNAL_SELL  # noqa: E402
from app.core.signal_engine import MAX_RISK_PCT, SETUP_RR, analyze_ticker  # noqa: E402
from app.providers.base import Bar  # noqa: E402

_ctx = SignalContext(regime="neutral", backtest_win_rates={})
_START = date(2025, 1, 1)


def _bars(pcts, start: float = 100.0, volume: float = 1_000_000.0, last_volume: float | None = None):
    """Build a chronological bar series from a list of per-bar fractional moves.

    Wicks are proportional to the body so fractal pivots have unique extremes.
    ``last_volume`` spikes the final (entry) bar, which is how the volume
    confirmation booster is exercised.
    """
    out = []
    price = start
    for i, pct in enumerate(pcts):
        o = price
        c = price * (1.0 + pct)
        body = abs(c - o)
        hi = max(o, c) + 0.25 * body + 0.001 * price
        lo = min(o, c) - 0.25 * body - 0.001 * price
        vol = last_volume if (last_volume is not None and i == len(pcts) - 1) else volume
        out.append(
            Bar(
                date=_START + timedelta(days=i),
                open=o,
                high=hi,
                low=lo,
                close=c,
                volume=vol,
            )
        )
        price = c
    return out


def _wave(n, trend, amplitude=0.015, period=10.0):
    """Trending series with a regular oscillation, so swing pivots exist."""
    return [trend + amplitude * math.sin(2 * math.pi * i / period) for i in range(n)]


def _run(pcts, **bar_kwargs):
    bars = _bars(pcts, **bar_kwargs)
    return analyze_ticker("TEST", "Test Co", "Technology", bars, _ctx)


# Uptrend, shallow 3-bar pullback that holds above the 50 SMA, then a bullish EXE.
UC1_SERIES = _wave(80, 0.002) + [-0.004] * 3 + [0.010] * 2 + [0.025]
# Downtrend, shallow 3-bar pullback that holds below the 50 SMA, then a bearish EXE.
DC1_SERIES = _wave(80, -0.002) + [0.006] * 3 + [-0.010] * 2 + [-0.025]


class TestSmaStrategy(unittest.TestCase):
    def test_uc1_bullish_continuation_detected(self):
        drafts = _run(UC1_SERIES)
        self.assertTrue(drafts, "expected a UC1 continuation signal")
        d = drafts[0]
        self.assertEqual(d.setup, "UC1")
        self.assertEqual(d.direction, SIGNAL_BUY)
        self.assertLess(d.stop, d.entry)
        self.assertGreater(d.target, d.entry)

    def test_dc1_bearish_continuation_detected(self):
        drafts = _run(DC1_SERIES)
        self.assertTrue(drafts, "expected a DC1 continuation signal")
        d = drafts[0]
        self.assertEqual(d.setup, "DC1")
        self.assertEqual(d.direction, SIGNAL_SELL)
        self.assertGreater(d.stop, d.entry)
        self.assertLess(d.target, d.entry)

    def test_levels_sane_for_every_signal(self):
        for pcts in (UC1_SERIES, DC1_SERIES):
            for d in _run(pcts):
                self.assertGreater(d.entry, 0)
                self.assertGreater(d.stop, 0)
                self.assertGreater(d.target, 0)
                self.assertGreaterEqual(d.confidence, 0.0)
                self.assertLessEqual(d.confidence, 100.0)
                if d.direction == SIGNAL_BUY:
                    self.assertLess(d.stop, d.entry)
                    self.assertGreater(d.target, d.entry)
                else:
                    self.assertGreater(d.stop, d.entry)
                    self.assertLess(d.target, d.entry)

    def test_risk_reward_is_projected_from_the_stop(self):
        for pcts in (UC1_SERIES, DC1_SERIES):
            for d in _run(pcts):
                risk = abs(d.entry - d.stop)
                reward = abs(d.target - d.entry)
                self.assertAlmostEqual(reward / risk, SETUP_RR[d.setup], places=1)

    def test_structural_stop_stays_within_the_risk_guardrail(self):
        for pcts in (UC1_SERIES, DC1_SERIES):
            for d in _run(pcts):
                self.assertLessEqual(abs(d.entry - d.stop) / d.entry, MAX_RISK_PCT + 1e-9)

    def test_flat_series_produces_no_signal(self):
        self.assertEqual(_run([0.0] * 90), [])

    def test_confidence_is_a_blend_of_continuation_and_reversal(self):
        d = _run(UC1_SERIES)[0]
        c = d.confidence_components
        expected_keys = {
            "continuation",
            "reversal",
            "continuation_weight",
            "reversal_weight",
            "blend",
            "regime_adjustment",
            "sector_adjustment",
            "counter_impact",
            "final",
        }
        self.assertTrue(expected_keys.issubset(set(c.keys())), sorted(c.keys()))

        # The blend is the weighted mix of the two factor groups...
        expected_blend = (
            c["continuation"] * c["continuation_weight"] / 100.0
            + c["reversal"] * c["reversal_weight"] / 100.0
        )
        self.assertAlmostEqual(c["blend"], expected_blend, places=1)

        # ...and the final score is that blend plus the context adjustments.
        expected_final = max(
            0.0,
            min(
                100.0,
                c["blend"]
                + c["regime_adjustment"]
                + c["sector_adjustment"]
                + c["counter_impact"]
                + c["confirmation_boost"],
            ),
        )
        self.assertAlmostEqual(c["final"], expected_final, places=1)
        self.assertEqual(d.confidence, c["final"])

    def test_individual_factors_are_reported(self):
        c = _run(UC1_SERIES)[0].confidence_components
        for factor in ("trend_separation", "ma_alignment", "trigger_strength", "reversal_trigger"):
            self.assertIn(f"factor_{factor}", c)
            self.assertGreaterEqual(c[f"factor_{factor}"], 0.0)
            self.assertLessEqual(c[f"factor_{factor}"], 100.0)

    def test_family_weights_favour_the_setups_own_family(self):
        from app.core.sma_strategy import FAMILY_WEIGHTS

        for setup in ("UC1", "UC2", "DC1", "DC2"):
            cont, rev = FAMILY_WEIGHTS[setup]
            self.assertGreater(cont, rev, f"{setup} should favour continuation evidence")
        for setup in ("UR1", "DR1", "UR2", "DR2"):
            cont, rev = FAMILY_WEIGHTS[setup]
            self.assertLess(cont, rev, f"{setup} should favour reversal evidence")

    def test_opposing_macro_sentiment_lowers_confidence(self):
        bars = _bars(UC1_SERIES)
        supportive = analyze_ticker(
            "TEST", "Test Co", "Technology", bars,
            SignalContext(regime="bullish", macro_sentiment=0.8),
        )
        opposed = analyze_ticker(
            "TEST", "Test Co", "Technology", bars,
            SignalContext(regime="bearish", macro_sentiment=-0.8),
        )
        self.assertTrue(supportive, "expected a signal with a supportive backdrop")
        self.assertTrue(opposed, "expected a signal with an opposing backdrop")
        self.assertGreater(supportive[0].confidence, opposed[0].confidence)
        self.assertLess(opposed[0].confidence_components["counter_impact"], 0.0)
        self.assertGreater(supportive[0].confidence_components["counter_impact"], 0.0)

    def test_counter_impact_direction_follows_the_trade(self):
        from app.core.constants import SIGNAL_BUY, SIGNAL_SELL
        from app.core.sma_strategy import _counter_impact

        negative_calendar = SignalContext(macro_sentiment=-0.8)
        # A weak calendar argues against a long and supports a short.
        self.assertLess(_counter_impact(SIGNAL_BUY, "Technology", negative_calendar), 0.0)
        self.assertGreater(_counter_impact(SIGNAL_SELL, "Technology", negative_calendar), 0.0)

    def test_counter_impact_is_bounded(self):
        from app.core.constants import SIGNAL_BUY
        from app.core.sma_strategy import COUNTER_IMPACT_MAX, COUNTER_IMPACT_MIN, _counter_impact

        worst = SignalContext(
            macro_sentiment=-1.0,
            high_impact_events_within_2d=True,
            rate_rising_sharply=True,
            earnings_in_days=2,
        )
        value = _counter_impact(SIGNAL_BUY, "Real Estate", worst)
        self.assertGreaterEqual(value, COUNTER_IMPACT_MIN)
        self.assertLessEqual(value, COUNTER_IMPACT_MAX)

    def test_counter_drivers_explain_the_impact(self):
        from app.core.constants import SIGNAL_BUY
        from app.core.sma_strategy import _counter_drivers

        ctx = SignalContext(
            macro_sentiment=-0.5, high_impact_events_within_2d=True, earnings_in_days=3
        )
        drivers = _counter_drivers(SIGNAL_BUY, "Technology", ctx)
        self.assertTrue(drivers)
        self.assertTrue(any("opposes" in d for d in drivers))
        self.assertTrue(any("high-impact" in d for d in drivers))
        self.assertTrue(any("earnings" in d for d in drivers))

    def test_short_series_is_ignored(self):
        self.assertEqual(_run([0.004] * 20), [])

    def test_never_returns_conflicting_directions(self):
        for pcts in (UC1_SERIES, DC1_SERIES):
            drafts = _run(pcts)
            self.assertLessEqual(len(drafts), 1)

    def test_sell_setup_is_flagged_for_options(self):
        drafts = _run(DC1_SERIES)
        self.assertTrue(drafts)
        d = drafts[0]
        self.assertEqual(d.event_flags.get("direction"), SIGNAL_SELL)
        self.assertEqual(d.event_flags.get("setup"), d.setup)


    # -- volume and Average True Range confirmation -----------------------
    def test_volume_backing_adds_confidence(self):
        quiet = _run(UC1_SERIES)[0]
        backed = _run(UC1_SERIES, last_volume=4_000_000.0)[0]
        self.assertGreater(
            backed.confidence_components["confirmation_boost"],
            quiet.confidence_components["confirmation_boost"],
        )
        self.assertGreater(backed.confidence, quiet.confidence)

    def test_average_volume_earns_no_volume_credit(self):
        from app.core.sma_strategy import (
            VOLUME_CONFIRMATION_FULL,
            VOLUME_CONFIRMATION_MIN,
            _scale,
        )

        self.assertEqual(_scale(1.0, VOLUME_CONFIRMATION_MIN, VOLUME_CONFIRMATION_FULL), 0.0)

    def test_confirmation_boost_thresholds(self):
        from app.core.sma_strategy import CONFIRMATION_BOOST_MAX, _confirmation_boost

        # Below both floors, and exactly at them, nothing is added.
        self.assertEqual(_confirmation_boost(0.9, 0.7), 0.0)
        self.assertEqual(_confirmation_boost(1.0, 0.8), 0.0)
        # Fully backed on both legs earns the maximum.
        self.assertEqual(_confirmation_boost(2.0, 1.6), CONFIRMATION_BOOST_MAX)
        self.assertEqual(_confirmation_boost(3.0, 2.5), CONFIRMATION_BOOST_MAX)
        # Partly backed earns a partial share.
        partial = _confirmation_boost(1.5, 1.2)
        self.assertGreater(partial, 0.0)
        self.assertLess(partial, CONFIRMATION_BOOST_MAX)
        # The legs are independent: heavy volume alone still earns something.
        self.assertGreater(_confirmation_boost(2.0, 0.5), 0.0)
        self.assertGreater(_confirmation_boost(0.5, 1.6), 0.0)

    def test_confirmation_boost_is_never_negative(self):
        from app.core.sma_strategy import _confirmation_boost

        self.assertEqual(_confirmation_boost(0.0, 0.0), 0.0)
        self.assertGreaterEqual(_confirmation_boost(0.4, 0.2), 0.0)

    def test_volume_and_range_readings_are_reported(self):
        d = _run(UC1_SERIES, last_volume=4_000_000.0)[0]
        c = d.confidence_components
        self.assertIn("volume_ratio", c)
        self.assertIn("atr_multiple", c)
        self.assertGreater(c["volume_ratio"], 1.0)
        self.assertGreater(c["atr_multiple"], 1.0)

    def test_volume_and_range_are_continuation_factors(self):
        c = _run(UC1_SERIES, last_volume=4_000_000.0)[0].confidence_components
        self.assertIn("factor_volume_confirmation", c)
        self.assertIn("factor_volatility_expansion", c)


if __name__ == "__main__":
    unittest.main()
