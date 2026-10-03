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


def _bars(pcts, start: float = 100.0):
    """Build a chronological bar series from a list of per-bar fractional moves.

    Wicks are proportional to the body so fractal pivots have unique extremes.
    """
    out = []
    price = start
    for i, pct in enumerate(pcts):
        o = price
        c = price * (1.0 + pct)
        body = abs(c - o)
        hi = max(o, c) + 0.25 * body + 0.001 * price
        lo = min(o, c) - 0.25 * body - 0.001 * price
        out.append(
            Bar(
                date=_START + timedelta(days=i),
                open=o,
                high=hi,
                low=lo,
                close=c,
                volume=1_000_000.0,
            )
        )
        price = c
    return out


def _wave(n, trend, amplitude=0.015, period=10.0):
    """Trending series with a regular oscillation, so swing pivots exist."""
    return [trend + amplitude * math.sin(2 * math.pi * i / period) for i in range(n)]


def _run(pcts):
    bars = _bars(pcts)
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

    def test_confidence_components_present(self):
        drafts = _run(UC1_SERIES)
        self.assertTrue(drafts)
        keys = {"technical", "backtest", "regime", "sector", "volume", "macro"}
        self.assertTrue(keys.issubset(set(drafts[0].confidence_components.keys())))

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


if __name__ == "__main__":
    unittest.main()
