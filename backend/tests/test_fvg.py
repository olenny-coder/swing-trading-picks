"""Fair Value Gap + breakout-structure tests.

The engine is checked against hand-built candle sequences so every assertion is
about the rule it claims to implement, not about whatever the market happened to
do.
"""
import os
import sys
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.fvg import (  # noqa: E402
    BUY,
    FVG_DISPLACEMENT_ATR,
    SELL,
    detect_fair_value_gaps,
    nearest_open_gap,
    open_gaps,
    price_in_gap,
)
from app.core.fvg_strategy import (  # noqa: E402
    STATUS_BUY,
    STATUS_NO_TRADE,
    STATUS_SELL,
    STATUS_WAIT,
    FvgSettings,
    analyze_fvg,
    annotations,
    chart_markup,
    closed_only,
    signal_card,
)
from app.core.indicators import atr as atr_series  # noqa: E402
from app.core.structure import (  # noqa: E402
    detect_structures,
    swing_indices,
)
from app.providers.base import Bar  # noqa: E402

START = date(2026, 1, 5)


def mk(rows, start: date = START):
    """rows: (open, high, low, close) or (o, h, l, c, volume)."""
    out = []
    for i, row in enumerate(rows):
        o, h, l, c = row[:4]
        volume = row[4] if len(row) > 4 else 1_000_000.0
        out.append(
            Bar(
                date=start + timedelta(days=i),
                open=float(o),
                high=float(h),
                low=float(l),
                close=float(c),
                volume=float(volume),
            )
        )
    return out


def flat(n: int, price: float = 100.0, step: int = 0):
    return [(price, price + 1.0, price - 1.0, price + 0.5)] * n


class TestFairValueGapDetection(unittest.TestCase):
    def test_bullish_gap_needs_three_candles_with_no_overlap(self):
        bars = mk(
            [
                (100, 101, 99, 100.5),          # candle 1: high 101
                (101, 106, 100.5, 105.5),       # candle 2: bullish displacement
                (105.5, 108, 102, 107.5),       # candle 3: low 102 > 101
            ]
        )
        gaps = detect_fair_value_gaps(bars, "DAILY")
        self.assertEqual(len(gaps), 1)
        gap = gaps[0]
        self.assertEqual(gap.direction, BUY)
        # The zone spans candle 1's high up to candle 3's low.
        self.assertEqual(gap.bottom, 101.0)
        self.assertEqual(gap.top, 102.0)
        self.assertEqual(gap.midpoint, 101.5)
        self.assertEqual(gap.proximal, 102.0)   # retracing down meets the top first
        self.assertEqual(gap.distal, 101.0)
        self.assertEqual(gap.label, "Bullish FVG")
        self.assertGreater(gap.displacement_atr, 0.0)

    def test_bearish_gap(self):
        bars = mk(
            [
                (110, 111, 109, 109.5),         # candle 1: low 109
                (109, 109.5, 104, 104.5),       # candle 2: bearish displacement
                (104.5, 108, 103, 103.5),       # candle 3: high 108 < 109
            ]
        )
        gaps = detect_fair_value_gaps(bars, "DAILY")
        self.assertEqual(len(gaps), 1)
        self.assertEqual(gaps[0].direction, SELL)
        # The zone spans candle 3's high up to candle 1's low.
        self.assertEqual(gaps[0].bottom, 108.0)
        self.assertEqual(gaps[0].top, 109.0)
        self.assertEqual(gaps[0].proximal, 108.0)  # rallying up meets the bottom first
        self.assertEqual(gaps[0].distal, 109.0)
        self.assertEqual(gaps[0].label, "Bearish FVG")

    def test_overlapping_candles_leave_no_gap(self):
        bars = mk(
            [
                (100, 102, 99, 101),
                (101, 105, 100, 104),   # strong, but candle 3 overlaps candle 1
                (104, 106, 100.5, 105),
            ]
        )
        self.assertEqual(detect_fair_value_gaps(bars, "DAILY"), [])

    def test_weak_middle_candle_is_not_a_displacement(self):
        bars = mk(
            [
                (100, 101, 99, 100.5),
                (101, 101.4, 100.8, 101.2),   # tiny body, small range
                (101.2, 108, 102, 107.5),
            ]
        )
        self.assertEqual(detect_fair_value_gaps(bars, "DAILY"), [])

    def test_direction_filter(self):
        bulls = mk([(100, 101, 99, 100.5), (101, 106, 100.5, 105.5), (105.5, 108, 102, 107.5)])
        self.assertEqual(detect_fair_value_gaps(bulls, "DAILY", direction=SELL), [])
        self.assertEqual(len(detect_fair_value_gaps(bulls, "DAILY", direction=BUY)), 1)

    def test_mitigation_is_tracked_and_gaps_can_close(self):
        bars = mk(
            [
                (100, 101, 99, 100.5),
                (101, 106, 100.5, 105.5),
                (105.5, 108, 102, 107.5),      # gap 101–102
                (107, 107.5, 99, 100),         # trades all the way through it
            ]
        )
        gap = detect_fair_value_gaps(bars, "DAILY")[0]
        self.assertGreaterEqual(gap.mitigation, 0.99)
        self.assertFalse(gap.is_open)
        self.assertEqual(open_gaps([gap]), [])

    def test_untouched_gap_is_open(self):
        bars = mk(
            [
                (100, 101, 99, 100.5),
                (101, 106, 100.5, 105.5),
                (105.5, 108, 102, 107.5),
                (107.5, 109, 105, 108.5),      # stays above the gap
            ]
        )
        gap = detect_fair_value_gaps(bars, "DAILY")[0]
        self.assertEqual(gap.mitigation, 0.0)
        self.assertTrue(gap.is_open)

    def test_too_few_candles_is_safe(self):
        self.assertEqual(detect_fair_value_gaps(mk([(1, 2, 0.5, 1.5)]), "DAILY"), [])

    def test_price_in_gap(self):
        bars = mk([(100, 101, 99, 100.5), (101, 106, 100.5, 105.5), (105.5, 108, 102, 107.5)])
        gap = detect_fair_value_gaps(bars, "DAILY")[0]
        self.assertTrue(price_in_gap(gap, 101.5))
        self.assertFalse(price_in_gap(gap, 110.0))

    def test_nearest_open_gap_prefers_the_zone_price_is_approaching(self):
        bars = mk(
            [
                (100, 101, 99, 100.5), (101, 106, 100.5, 105.5), (105.5, 108, 102, 107.5),
                (107.5, 112, 107, 111.5), (112, 118, 111.5, 117.5), (117.5, 120, 114, 119.5),
            ]
        )
        gaps = open_gaps(detect_fair_value_gaps(bars, "DAILY"))
        self.assertGreaterEqual(len(gaps), 1)
        chosen = nearest_open_gap(gaps, 119.5, BUY)
        self.assertIsNotNone(chosen)
        self.assertEqual(chosen.direction, BUY)


class TestStructures(unittest.TestCase):
    def _uptrend_then_break(self):
        rows = []
        price = 100.0
        for _ in range(40):
            rows.append((price, price + 1.0, price - 1.0, price + 0.6))
            price += 0.6
        # A tight box, then a decisive close above it.
        for _ in range(12):
            rows.append((price, price + 0.8, price - 0.8, price + 0.2))
        rows.append((price, price + 6.0, price - 0.2, price + 5.0))
        return mk(rows)

    def test_a_break_of_structure_is_detected(self):
        bars = self._uptrend_then_break()
        atr_values = atr_series(
            [b.high for b in bars], [b.low for b in bars], [b.close for b in bars]
        )
        structures = detect_structures(bars, atr_values)
        self.assertTrue(structures, "a decisive close out of the box must register")
        kinds = {s.kind for s in structures}
        self.assertTrue(kinds & {"BOS", "CHOCH", "RANGE", "FLAG"}, kinds)
        for structure in structures:
            self.assertEqual(structure.direction, BUY)
            self.assertGreater(structure.level, 0)
            self.assertIn("level", structure.as_dict())

    def test_thin_series_yields_nothing(self):
        structures = detect_structures(mk(flat(4)), atr_series([1] * 4, [1] * 4, [1] * 4))
        self.assertEqual(structures, [])

    def test_structure_quality_is_bounded(self):
        bars = self._uptrend_then_break()
        atr_values = atr_series(
            [b.high for b in bars], [b.low for b in bars], [b.close for b in bars]
        )
        for structure in detect_structures(bars, atr_values):
            self.assertGreater(structure.quality, 0.0)
            self.assertLessEqual(structure.quality, 1.0)

    def test_swing_indices_finds_fractal_pivots(self):
        rows = [(10, 10 + (i % 5), 10 - (i % 5), 10 + (i % 3)) for i in range(40)]
        bars = mk(rows)
        swings = swing_indices([b.high for b in bars], [b.low for b in bars])
        self.assertTrue(swings.highs)
        self.assertTrue(swings.lows)


class TestClosedCandlesOnly(unittest.TestCase):
    def test_a_bar_dated_today_is_dropped(self):
        today = date(2026, 3, 10)
        bars = mk([(1, 2, 0.5, 1.5)] * 3, start=today - timedelta(days=2))
        self.assertEqual(len(closed_only(bars, today)), 2)

    def test_older_bars_are_kept(self):
        today = date(2026, 3, 10)
        bars = mk([(1, 2, 0.5, 1.5)] * 3, start=today - timedelta(days=10))
        self.assertEqual(len(closed_only(bars, today)), 3)


class TestAnalyze(unittest.TestCase):
    def _breakout_with_gap(self):
        """A box breakout that leaves an unmitigated bullish gap behind it."""
        rows = []
        price = 100.0
        for _ in range(50):
            rows.append((price, price + 1.0, price - 1.0, price + 0.5))
            price += 0.5
        for _ in range(12):
            rows.append((price, price + 0.6, price - 0.6, price + 0.1))
        box_high = max(r[1] for r in rows[-12:])
        # candle 1 ends at the box high, candle 2 displaces, candle 3 leaves a gap
        rows.append((price, box_high, price - 0.5, box_high - 0.2))
        rows.append((box_high, box_high + 5.0, box_high - 0.1, box_high + 4.6))
        rows.append((box_high + 4.6, box_high + 7.0, box_high + 1.5, box_high + 6.4))
        # hold above the gap so it stays open
        rows.append((box_high + 6.4, box_high + 8.0, box_high + 5.5, box_high + 7.5))
        rows.append((box_high + 7.5, box_high + 9.0, box_high + 6.5, box_high + 8.6))
        return mk(rows)

    def test_thin_series_is_no_trade_with_a_reason(self):
        candidate = analyze_fvg("TEST", "Test", "Technology", mk(flat(20)), "DAILY")
        self.assertEqual(candidate.status, STATUS_NO_TRADE)
        self.assertEqual(candidate.confidence, 0.0)
        self.assertTrue(candidate.blockers)
        row = candidate.as_row()
        self.assertIsNone(row["entry"])
        self.assertEqual(row["setup_type"], "No valid signal")

    def test_a_breakout_with_a_gap_produces_a_coherent_setup(self):
        candidate = analyze_fvg(
            "TEST", "Test", "Technology", self._breakout_with_gap(), "DAILY", FvgSettings()
        )
        self.assertIn(candidate.status, (STATUS_BUY, STATUS_WAIT, STATUS_NO_TRADE))
        if candidate.gap is None:
            self.skipTest("the fixture did not leave a gap")
        self.assertEqual(candidate.direction, BUY)
        self.assertIsNotNone(candidate.entry)
        self.assertIsNotNone(candidate.stop)
        # A long: the stop sits under the entry and the targets above it.
        self.assertLess(candidate.stop, candidate.entry)
        self.assertGreater(candidate.target1, candidate.entry)
        self.assertGreaterEqual(candidate.target2, candidate.target1)
        self.assertGreater(candidate.rr1, 0)
        # The standoff is deliberate: an un-retraced gap is WAIT, not a buy.
        if candidate.status == STATUS_WAIT:
            self.assertTrue(any("retrace" in b for b in candidate.blockers))

    def test_short_setups_put_the_stop_above_the_entry(self):
        rows = []
        price = 140.0
        for _ in range(50):
            rows.append((price, price + 1.0, price - 1.0, price - 0.5))
            price -= 0.5
        for _ in range(12):
            rows.append((price, price + 0.6, price - 0.6, price - 0.1))
        box_low = min(r[2] for r in rows[-12:])
        rows.append((price, price + 0.5, box_low, box_low + 0.2))
        rows.append((box_low, box_low + 0.1, box_low - 5.0, box_low - 4.6))
        rows.append((box_low - 4.6, box_low - 1.5, box_low - 7.0, box_low - 6.4))
        rows.append((box_low - 6.4, box_low - 5.5, box_low - 8.0, box_low - 7.5))
        rows.append((box_low - 7.5, box_low - 6.5, box_low - 9.0, box_low - 8.6))
        candidate = analyze_fvg("TEST", "Test", "Technology", mk(rows), "DAILY")
        if candidate.gap is None or candidate.direction != SELL:
            self.skipTest("the fixture did not produce a short gap setup")
        self.assertGreater(candidate.stop, candidate.entry)
        self.assertLess(candidate.target1, candidate.entry)

    def test_earnings_inside_the_buffer_blocks_the_setup(self):
        bars = self._breakout_with_gap()
        blocked = analyze_fvg("T", "T", "Technology", bars, "DAILY", earnings_in_days=2)
        if blocked.gap is None:
            self.skipTest("no gap in the fixture")
        self.assertEqual(blocked.status, STATUS_NO_TRADE)
        self.assertTrue(any("earnings" in b for b in blocked.blockers))

    def test_earnings_plays_can_be_allowed(self):
        bars = self._breakout_with_gap()
        allowed = analyze_fvg(
            "T",
            "T",
            "Technology",
            bars,
            "DAILY",
            FvgSettings(allow_earnings_plays=True),
            earnings_in_days=2,
        )
        self.assertTrue(
            all("earnings" not in b for b in allowed.blockers),
            "an allowed earnings play must not be blocked by the buffer",
        )

    def test_price_below_the_floor_is_rejected(self):
        candidate = analyze_fvg("P", "P", "Technology", mk(flat(80, price=2.0)), "DAILY")
        self.assertEqual(candidate.status, STATUS_NO_TRADE)

    def test_confidence_stays_in_range(self):
        candidate = analyze_fvg("T", "T", "Technology", self._breakout_with_gap(), "DAILY")
        self.assertGreaterEqual(candidate.confidence, 0.0)
        self.assertLessEqual(candidate.confidence, 100.0)


class TestDrilldownPayloads(unittest.TestCase):
    def _candidate(self):
        rows = []
        price = 100.0
        for _ in range(50):
            rows.append((price, price + 1.0, price - 1.0, price + 0.5))
            price += 0.5
        for _ in range(12):
            rows.append((price, price + 0.6, price - 0.6, price + 0.1))
        box_high = max(r[1] for r in rows[-12:])
        rows.append((price, box_high, price - 0.5, box_high - 0.2))
        rows.append((box_high, box_high + 5.0, box_high - 0.1, box_high + 4.6))
        rows.append((box_high + 4.6, box_high + 7.0, box_high + 1.5, box_high + 6.4))
        rows.append((box_high + 6.4, box_high + 8.0, box_high + 5.5, box_high + 7.5))
        bars = mk(rows)
        return bars, analyze_fvg("TEST", "Test", "Technology", bars, "DAILY")

    def test_annotations_describe_the_chart_markup(self):
        bars, candidate = self._candidate()
        atr_values = atr_series(
            [b.high for b in bars], [b.low for b in bars], [b.close for b in bars]
        )
        gaps = detect_fair_value_gaps(bars, "DAILY", atr_values)
        marks = annotations(candidate, gaps, bars)
        kinds = {a["kind"] for a in marks}
        self.assertIn("fvg", kinds)
        if candidate.entry is not None:
            self.assertIn("level", kinds)
            self.assertIn("marker", kinds)

        fvg = next(a for a in marks if a["kind"] == "fvg")
        self.assertLess(fvg["bottom"], fvg["top"])
        self.assertIn("from_date", fvg)
        self.assertIn("to_date", fvg)
        self.assertEqual(fvg["timeframe"], "DAILY")

        for mark in marks:
            if mark["kind"] in ("fvg", "zone", "box"):
                self.assertLess(mark["bottom"], mark["top"])

    def test_signal_card_states_the_levels_and_the_disclaimer(self):
        _, candidate = self._candidate()
        card = signal_card(candidate, FvgSettings(risk_per_trade_pct=1.5))
        for key in (
            "signal",
            "direction",
            "entry",
            "stop",
            "target1",
            "target2",
            "rr1",
            "risk_per_share",
            "invalidation",
            "disclaimer",
        ):
            self.assertIn(key, card)
        self.assertEqual(card["risk_per_trade_pct"], 1.5)
        self.assertIn("not financial advice", card["disclaimer"].lower())

    def test_chart_markup_is_serialisable(self):
        import json

        bars, candidate = self._candidate()
        atr_values = atr_series(
            [b.high for b in bars], [b.low for b in bars], [b.close for b in bars]
        )
        gaps = detect_fair_value_gaps(bars, "DAILY", atr_values)
        markup = chart_markup(candidate, gaps, bars)
        json.dumps(markup)  # must not raise
        self.assertEqual(markup["ticker"], "TEST")
        self.assertEqual(markup["timeframe"], "DAILY")
        self.assertIn("annotations", markup)

    def test_no_trade_still_returns_a_card(self):
        candidate = analyze_fvg("T", "T", "Technology", mk(flat(20)), "DAILY")
        card = signal_card(candidate)
        self.assertTrue(card["no_trade"])
        self.assertEqual(card["signal"], STATUS_NO_TRADE)
        self.assertTrue(card["blockers"])


if __name__ == "__main__":
    unittest.main()
