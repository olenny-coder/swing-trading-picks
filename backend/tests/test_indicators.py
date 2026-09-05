"""Unit tests for technical indicators."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core import indicators as ta  # noqa: E402


class TestIndicators(unittest.TestCase):
    def test_sma(self):
        out = ta.sma([1, 2, 3, 4, 5], 3)
        self.assertIsNone(out[0])
        self.assertIsNone(out[1])
        self.assertEqual(out[2], 2.0)
        self.assertEqual(out[3], 3.0)
        self.assertEqual(out[4], 4.0)

    def test_ema_monotonic(self):
        closes = [float(i) for i in range(1, 60)]
        e = ta.ema(closes, 20)
        self.assertIsNotNone(e[-1])
        self.assertGreater(e[-1], e[19])  # rising series -> EMA rising

    def test_macd_shapes(self):
        closes = [100 + i for i in range(100)]
        macd, sig, hist = ta.macd(closes)
        self.assertEqual(len(macd), 100)
        self.assertEqual(len(sig), 100)
        self.assertEqual(len(hist), 100)
        self.assertIsNotNone(macd[-1])
        self.assertIsNotNone(sig[-1])

    def test_rsi_bounds(self):
        up = [100 + i for i in range(40)]
        rsi_up = ta.rsi(up)
        self.assertIsNotNone(rsi_up[-1])
        self.assertGreaterEqual(rsi_up[-1], 0)
        self.assertLessEqual(rsi_up[-1], 100)

    def test_atr_positive(self):
        highs = [10 + i * 0.1 for i in range(40)]
        lows = [9 + i * 0.1 for i in range(40)]
        closes = [9.5 + i * 0.1 for i in range(40)]
        a = ta.atr(highs, lows, closes)
        self.assertIsNotNone(a[-1])
        self.assertGreater(a[-1], 0)

    def test_is_doji_true(self):
        # Tiny body, long symmetric shadows.
        self.assertTrue(ta.is_doji(100.1, 103.0, 97.0, 100.0))

    def test_is_doji_false_momentum_candle(self):
        self.assertFalse(ta.is_doji(98.0, 103.0, 97.5, 102.5))

    def test_crossed_above(self):
        a = [1, 2, 1, 3, 4]
        b = [1.5, 1.5, 1.5, 1.5, 1.5]
        self.assertTrue(ta.crossed_above(a, b, within=3))
        # b never exceeds a here (a stays above b), so no upward cross.
        a2 = [2, 3, 4, 5, 6]
        b2 = [1, 1, 1, 1, 1]
        self.assertFalse(ta.crossed_above(b2, a2, within=3))


if __name__ == "__main__":
    unittest.main()
