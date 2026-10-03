"""Retrospective accuracy tests: did a pick reach target or stop?"""
import os
import sys
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.constants import SIGNAL_BUY, SIGNAL_SELL  # noqa: E402
from app.providers.base import Bar  # noqa: E402
from app.services.outcome_service import (  # noqa: E402
    EXPIRED,
    OPEN,
    STOP_HIT,
    TARGET_HIT,
    evaluate,
)

DAY = date(2026, 3, 2)


def _series(rows, start: date = DAY):
    """rows: (open, high, low, close) tuples, one per consecutive session."""
    return [
        Bar(
            date=start + timedelta(days=i),
            open=o,
            high=h,
            low=l,
            close=c,
            volume=1_000.0,
        )
        for i, (o, h, l, c) in enumerate(rows)
    ]


class TestEvaluate(unittest.TestCase):
    def test_bullish_target_reached(self):
        bars = _series([(100, 106, 99, 105)])
        out = evaluate(SIGNAL_BUY, 100, 105, 95, bars)
        self.assertEqual(out["status"], TARGET_HIT)
        self.assertEqual(out["exit_price"], 105)
        self.assertAlmostEqual(out["pnl_pct"], 5.0, places=2)
        self.assertEqual(out["bars_held"], 1)

    def test_bullish_stop_reached(self):
        bars = _series([(100, 101, 94, 95)])
        out = evaluate(SIGNAL_BUY, 100, 105, 95, bars)
        self.assertEqual(out["status"], STOP_HIT)
        self.assertAlmostEqual(out["pnl_pct"], -5.0, places=2)

    def test_a_candle_spanning_both_levels_counts_as_the_stop(self):
        """Conservative: an ambiguous bar must not flatter the win rate."""
        bars = _series([(100, 108, 92, 100)])
        out = evaluate(SIGNAL_BUY, 100, 105, 95, bars)
        self.assertEqual(out["status"], STOP_HIT)

    def test_bearish_target_reached(self):
        bars = _series([(100, 101, 94, 95)])
        out = evaluate(SIGNAL_SELL, 100, 95, 105, bars)
        self.assertEqual(out["status"], TARGET_HIT)
        self.assertAlmostEqual(out["pnl_pct"], 5.0, places=2)

    def test_bearish_stop_reached(self):
        bars = _series([(100, 106, 99, 105)])
        out = evaluate(SIGNAL_SELL, 100, 95, 105, bars)
        self.assertEqual(out["status"], STOP_HIT)
        self.assertAlmostEqual(out["pnl_pct"], -5.0, places=2)

    def test_stop_wins_when_it_comes_first(self):
        bars = _series([(100, 101, 94, 95), (95, 112, 95, 110)])
        out = evaluate(SIGNAL_BUY, 100, 105, 95, bars)
        self.assertEqual(out["status"], STOP_HIT)
        self.assertEqual(out["bars_held"], 1)

    def test_target_wins_when_it_comes_first(self):
        bars = _series([(100, 106, 99, 105), (105, 106, 80, 82)])
        out = evaluate(SIGNAL_BUY, 100, 105, 95, bars)
        self.assertEqual(out["status"], TARGET_HIT)
        self.assertEqual(out["bars_held"], 1)

    def test_unresolved_within_the_horizon_is_open(self):
        bars = _series([(100, 101, 99, 100)] * 3)
        out = evaluate(SIGNAL_BUY, 100, 120, 80, bars, "DAILY")
        self.assertEqual(out["status"], OPEN)
        self.assertEqual(out["bars_held"], 3)

    def test_unresolved_past_the_horizon_expires(self):
        daily_horizon = 10
        bars = _series([(100, 101, 99, 100)] * (daily_horizon + 4))
        out = evaluate(SIGNAL_BUY, 100, 120, 80, bars, "DAILY")
        self.assertEqual(out["status"], EXPIRED)
        self.assertEqual(out["bars_held"], daily_horizon)

    def test_weekly_picks_get_a_longer_horizon(self):
        from app.services.outcome_service import horizon_days

        self.assertGreater(horizon_days("WEEKLY"), horizon_days("DAILY"))
        self.assertGreater(horizon_days("MONTHLY"), horizon_days("WEEKLY"))

    def test_excursions_are_recorded(self):
        bars = _series([(100, 104, 97, 101), (101, 106, 100, 105)])
        out = evaluate(SIGNAL_BUY, 100, 105, 95, bars)
        self.assertGreaterEqual(out["max_favourable_pct"], 5.0)
        self.assertGreaterEqual(out["max_adverse_pct"], 3.0)

    def test_empty_bars_yield_no_outcome(self):
        self.assertIsNone(evaluate(SIGNAL_BUY, 100, 105, 95, []))


class TestAccuracySummary(unittest.TestCase):
    def test_summary_counts_and_win_rate(self):
        from app.services import outcome_service

        class FakeSignal:
            def __init__(self, setup, outcome):
                self.setup = setup
                self.outcome = outcome

        rows = [
            FakeSignal("UC1", {"status": TARGET_HIT, "pnl_pct": 6.0}),
            FakeSignal("UC1", {"status": STOP_HIT, "pnl_pct": -3.0}),
            FakeSignal("DC1", {"status": TARGET_HIT, "pnl_pct": 4.0}),
            FakeSignal("DC1", {"status": OPEN, "pnl_pct": 0.5}),
        ]

        class FakeQuery:
            def filter(self, *args, **kwargs):
                return self

            def all(self):
                return rows

        class FakeSession:
            def query(self, *args, **kwargs):
                return FakeQuery()

        summary = outcome_service.accuracy_summary(FakeSession(), "DAILY")  # type: ignore[arg-type]
        self.assertEqual(summary["evaluated"], 4)
        self.assertEqual(summary["target_hit"], 2)
        self.assertEqual(summary["stop_hit"], 1)
        self.assertEqual(summary["open"], 1)
        self.assertEqual(summary["decided"], 3)
        self.assertAlmostEqual(summary["win_rate_pct"], 66.7, places=1)
        self.assertIsNotNone(summary["avg_win_pct"])
        self.assertIsNotNone(summary["avg_loss_pct"])

        by_setup = {row["setup"]: row for row in summary["by_setup"]}
        self.assertEqual(by_setup["UC1"]["win_rate_pct"], 50.0)
        self.assertEqual(by_setup["DC1"]["win_rate_pct"], 100.0)


if __name__ == "__main__":
    unittest.main()
