"""Integration tests for the signal engine against the MOCK provider."""
import os
import sys
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.base_types import SignalContext  # noqa: E402
from app.core.constants import (  # noqa: E402
    SIGNAL_BUY_DOJI_REVERSAL,
    SIGNAL_BUY_STANDARD,
    SIGNAL_SELL,
)
from app.core.signal_engine import analyze_ticker  # noqa: E402
from app.providers.mock_provider import (  # noqa: E402
    HERO_BUY_MOD,
    HERO_DOJI_MOD,
    HERO_PUT_MOD,
    UNIVERSE,
    MockMarketDataProvider,
    _hero_type,
)

_provider = MockMarketDataProvider()
_end = date.today()
_start = _end - timedelta(days=540)
_ctx = SignalContext(regime="neutral", backtest_win_rates={})


def _first_hero(mod: int):
    for ticker, name, sector in UNIVERSE:
        if _hero_type(ticker) == mod:
            return ticker, name, sector
    raise AssertionError(f"no hero ticker for mod {mod}")


def _heroes(mod: int):
    return [(t, n, s) for t, n, s in UNIVERSE if _hero_type(t) == mod]


def _assert_any_hero_fires(testcase, mod, signal_type):
    for ticker, name, sector in _heroes(mod):
        bars = _provider.get_daily_bars(ticker, _start, _end)
        drafts = analyze_ticker(ticker, name, sector, bars, _ctx)
        if any(d.type == signal_type for d in drafts):
            return
    testcase.fail(f"no hero ticker for mod {mod} produced {signal_type}")


class TestSignalEngine(unittest.TestCase):
    def test_buy_standard_detected(self):
        _assert_any_hero_fires(self, HERO_BUY_MOD, SIGNAL_BUY_STANDARD)

    def test_doji_reversal_detected(self):
        _assert_any_hero_fires(self, HERO_DOJI_MOD, SIGNAL_BUY_DOJI_REVERSAL)

    def test_sell_detected(self):
        _assert_any_hero_fires(self, HERO_PUT_MOD, SIGNAL_SELL)

    def test_buy_levels_sane(self):
        ticker, name, sector = _first_hero(HERO_BUY_MOD)
        bars = _provider.get_daily_bars(ticker, _start, _end)
        for d in analyze_ticker(ticker, name, sector, bars, _ctx):
            if d.type in (SIGNAL_BUY_STANDARD, SIGNAL_BUY_DOJI_REVERSAL):
                self.assertLess(d.stop, d.entry)
                self.assertGreater(d.target, d.entry)
                self.assertGreaterEqual(d.confidence, 0)
                self.assertLessEqual(d.confidence, 100)

    def test_sell_levels_sane(self):
        checked = False
        for ticker, name, sector in _heroes(HERO_PUT_MOD):
            bars = _provider.get_daily_bars(ticker, _start, _end)
            for d in analyze_ticker(ticker, name, sector, bars, _ctx):
                if d.type == SIGNAL_SELL:
                    checked = True
                    self.assertGreater(d.stop, d.entry)
                    self.assertLess(d.target, d.entry)
        self.assertTrue(checked, "expected at least one SELL signal")

    def test_confidence_has_all_components(self):
        ticker, name, sector = _first_hero(HERO_BUY_MOD)
        bars = _provider.get_daily_bars(ticker, _start, _end)
        drafts = analyze_ticker(ticker, name, sector, bars, _ctx)
        self.assertTrue(drafts)
        keys = {"technical", "backtest", "regime", "sector", "volume", "macro"}
        self.assertTrue(keys.issubset(set(drafts[0].confidence_components.keys())))


if __name__ == "__main__":
    unittest.main()
