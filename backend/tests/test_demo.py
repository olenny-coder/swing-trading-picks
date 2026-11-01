"""DEMO-mode tests: anonymous visitors must only ever see synthetic data.

The public read endpoints serve the cached demo dataset to callers who are not
signed in, and the real (database) rows only to a signed-in admin.
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(_tmp, 'demo.db')}"
os.environ["SECRET_KEY"] = "demo-test-secret-key-longer-than-32-bytes-1234"
os.environ["SEED_MODE"] = "sync"  # tests need the seed finished before the first request
os.environ["DATA_PROVIDER"] = "mock"
os.environ["ADMIN_USERNAME"] = "admin"
os.environ["ADMIN_PASSWORD"] = "testpass"

from fastapi.testclient import TestClient  # noqa: E402

from app.core.constants import SETUPS  # noqa: E402
from app.main import app  # noqa: E402
from app.services.demo_service import DEMO_ID_BASE  # noqa: E402


class TestTimeframeFiltering(unittest.TestCase):
    """The interval query parameter must actually reach the query.

    Regression guard: the filter dependency once omitted `timeframe`, so every
    interval silently returned the daily list.
    """

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    @staticmethod
    def _params(timeframe: str | None = None, setup: str | None = None) -> dict:
        params = {"limit": 100}
        if timeframe:
            params["timeframe"] = timeframe
        if setup:
            params["setup"] = setup
        return params

    def test_guest_daily_view_respects_the_interval(self):
        seen = {}
        for timeframe in ("DAILY", "WEEKLY", "MONTHLY"):
            body = self.client.get(
                "/api/signals/daily", params=self._params(timeframe)
            ).json()
            self.assertTrue(body["demo"])
            for signal in body["signals"]:
                self.assertEqual(signal["timeframe"], timeframe)
            seen[timeframe] = sorted(s["ticker"] for s in body["signals"])

        self.assertTrue(seen["DAILY"], "the demo should have daily picks")
        # The whole point of the filter: intervals are not the same list.
        self.assertNotEqual(seen["DAILY"], seen["WEEKLY"])

    def test_guest_history_respects_the_interval(self):
        for timeframe in ("DAILY", "WEEKLY"):
            body = self.client.get("/api/signals", params=self._params(timeframe)).json()
            self.assertTrue(body["signals"])
            for signal in body["signals"]:
                self.assertEqual(signal["timeframe"], timeframe)

    def test_setup_filter_is_applied(self):
        body = self.client.get("/api/signals", params=self._params("DAILY", "DC1")).json()
        self.assertTrue(body["signals"], "the demo should contain DC1 picks")
        for signal in body["signals"]:
            self.assertEqual(signal["setup"], "DC1")

    def test_an_unknown_interval_falls_back_to_daily(self):
        body = self.client.get("/api/signals/daily", params=self._params("FORTNIGHTLY")).json()
        for signal in body["signals"]:
            self.assertEqual(signal["timeframe"], "DAILY")

    def test_accuracy_respects_the_interval(self):
        daily = self.client.get("/api/signals/accuracy", params={"timeframe": "DAILY"}).json()
        weekly = self.client.get("/api/signals/accuracy", params={"timeframe": "WEEKLY"}).json()
        self.assertEqual(daily["timeframe"], "DAILY")
        self.assertEqual(weekly["timeframe"], "WEEKLY")

    def test_demo_ids_never_collide_with_real_ones(self):
        body = self.client.get("/api/signals", params=self._params("DAILY")).json()
        for signal in body["signals"]:
            self.assertGreaterEqual(signal["id"], DEMO_ID_BASE)

    def test_every_demo_signal_uses_a_known_setup(self):
        for timeframe in ("DAILY", "WEEKLY", "MONTHLY"):
            body = self.client.get("/api/signals", params=self._params(timeframe)).json()
            for signal in body["signals"]:
                self.assertIn(signal["setup"], SETUPS)

    def test_detail_chart_uses_the_signals_own_interval(self):
        """A weekly pick must chart weekly candles, not daily ones."""
        for timeframe in ("DAILY", "WEEKLY"):
            listing = self.client.get("/api/signals", params=self._params(timeframe)).json()
            if not listing["signals"]:
                continue
            signal_id = listing["signals"][0]["id"]
            detail = self.client.get(f"/api/signals/{signal_id}").json()
            self.assertEqual(detail["signal"]["timeframe"], timeframe)
            bars = detail["bars"]
            self.assertTrue(bars, f"expected chart bars for {timeframe}")
            if timeframe == "DAILY" or len(bars) < 3:
                continue
            # Consecutive weekly candles are about seven days apart; daily ones
            # (the old behaviour) would be one or two.
            from datetime import date as _date

            gaps = [
                (_date.fromisoformat(bars[i + 1]["date"]) - _date.fromisoformat(bars[i]["date"])).days
                for i in range(min(5, len(bars) - 1))
            ]
            self.assertGreaterEqual(
                min(gaps), 5, f"weekly candles should be about a week apart, got {gaps}"
            )


class TestDemoMode(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.client.__enter__()  # seeds the "real" rows via the MOCK provider

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def _auth_headers(self) -> dict:
        resp = self.client.post(
            "/api/auth/login", json={"username": "admin", "password": "testpass"}
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        return {"Authorization": f"Bearer {resp.json()['access_token']}"}

    # -- anonymous ---------------------------------------------------------
    def test_anonymous_daily_view_is_demo(self):
        resp = self.client.get("/api/signals/daily")
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertTrue(body["demo"], "anonymous callers must get the demo dataset")
        self.assertTrue(body["signals"], "the demo dataset should contain signals")
        for signal in body["signals"]:
            self.assertGreaterEqual(signal["id"], DEMO_ID_BASE)

    def test_anonymous_listing_is_demo(self):
        body = self.client.get("/api/signals").json()
        self.assertTrue(body["demo"])
        for signal in body["signals"]:
            self.assertGreaterEqual(signal["id"], DEMO_ID_BASE)

    def test_anonymous_summary_matches_demo_set(self):
        body = self.client.get("/api/signals/summary").json()
        self.assertIn("setup_counts", body)
        daily = self.client.get("/api/signals/daily").json()
        self.assertEqual(body["total_buys"], daily["summary"]["total_buys"])

    def test_anonymous_macro_dashboard_is_demo(self):
        body = self.client.get("/api/macro/dashboard").json()
        self.assertTrue(body["demo"])
        self.assertTrue(body["macro_events"], "the demo calendar should have events")
        self.assertIn("snapshot", body)

    def test_anonymous_can_open_a_demo_signal(self):
        listing = self.client.get("/api/signals/daily").json()
        demo_id = listing["signals"][0]["id"]
        resp = self.client.get(f"/api/signals/{demo_id}")
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertTrue(body["demo"])
        self.assertEqual(body["signal"]["id"], demo_id)
        self.assertTrue(body["bars"], "the demo detail should include chart bars")

    def test_anonymous_cannot_open_a_real_signal(self):
        """A real row id must not resolve for an anonymous visitor."""
        real_id = self._first_real_signal_id()
        resp = self.client.get(f"/api/signals/{real_id}")
        self.assertEqual(resp.status_code, 404, resp.text)
        self.assertIn("sign", resp.json()["detail"].lower())

    # -- signed in ---------------------------------------------------------
    def test_admin_daily_view_is_not_demo(self):
        body = self.client.get("/api/signals/daily", headers=self._auth_headers()).json()
        self.assertFalse(body["demo"], "a signed-in admin must get real data")
        for signal in body["signals"]:
            self.assertLess(signal["id"], DEMO_ID_BASE)

    def test_admin_macro_dashboard_is_not_demo(self):
        body = self.client.get("/api/macro/dashboard", headers=self._auth_headers()).json()
        self.assertFalse(body["demo"])

    def test_admin_can_open_a_real_signal(self):
        real_id = self._first_real_signal_id()
        resp = self.client.get(f"/api/signals/{real_id}", headers=self._auth_headers())
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertFalse(resp.json()["demo"])

    def test_bad_token_falls_back_to_demo_not_401(self):
        """An expired/garbage token should behave like a logged-out visitor."""
        resp = self.client.get(
            "/api/signals/daily", headers={"Authorization": "Bearer not-a-real-token"}
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertTrue(resp.json()["demo"])

    # -- helpers -----------------------------------------------------------
    def _first_real_signal_id(self) -> int:
        body = self.client.get("/api/signals/daily", headers=self._auth_headers()).json()
        self.assertTrue(body["signals"], "expected seeded real signals")
        return body["signals"][0]["id"]


class TestDemoDataset(unittest.TestCase):
    def test_dataset_is_cached(self):
        from app.services import demo_service

        demo_service.reset_cache()
        first = demo_service.dataset()
        second = demo_service.dataset()
        self.assertIs(first, second, "the demo dataset should be built once and cached")

    def test_demo_signal_ids_are_namespaced(self):
        from app.services import demo_service

        demo_service.reset_cache()
        data = demo_service.dataset()
        for timeframe, rows in data["signals"].items():
            for signal in rows:
                self.assertTrue(demo_service.is_demo_signal_id(signal["id"]))
                self.assertEqual(signal["timeframe"], timeframe)
        self.assertFalse(demo_service.is_demo_signal_id(1))

    def test_demo_covers_every_timeframe(self):
        """Every timeframe is present as a key; higher ones may legitimately be
        empty when no setup completed on the sample data."""
        from app.core.timeframes import TIMEFRAMES
        from app.services import demo_service

        demo_service.reset_cache()
        data = demo_service.dataset()
        self.assertEqual(set(data["signals"]), set(TIMEFRAMES))
        self.assertTrue(data["signals"]["DAILY"], "the daily demo list should not be empty")

    def test_demo_signals_carry_the_blended_confidence(self):
        from app.services import demo_service

        demo_service.reset_cache()
        data = demo_service.dataset()
        for rows in data["signals"].values():
            for signal in rows:
                components = signal["confidence_components"]
                self.assertIn("continuation", components)
                self.assertIn("reversal", components)
                self.assertIn("counter_impact", components)
                self.assertIn("confirmation_boost", components)
                self.assertEqual(components["final"], signal["confidence"])

    def test_demo_history_has_resolved_outcomes(self):
        """The demo must include past picks whose result is already known."""
        from app.services import demo_service

        demo_service.reset_cache()
        rows = demo_service.dataset()["signals"]["DAILY"]
        resolved = [s for s in rows if (s.get("outcome") or {}).get("status") in ("TARGET_HIT", "STOP_HIT")]
        self.assertTrue(resolved, "expected some demo picks to have resolved")
        for signal in resolved:
            outcome = signal["outcome"]
            self.assertIn(outcome["status"], ("TARGET_HIT", "STOP_HIT"))
            self.assertIsNotNone(outcome["pnl_pct"])
            self.assertIn("exit_date", outcome)

    def test_demo_accuracy_summary_is_consistent(self):
        from app.services import demo_service

        demo_service.reset_cache()
        summary = demo_service.accuracy_payload("DAILY")
        self.assertGreater(summary["evaluated"], 0)
        self.assertEqual(
            summary["decided"], summary["target_hit"] + summary["stop_hit"]
        )
        if summary["decided"]:
            self.assertIsNotNone(summary["win_rate_pct"])
            self.assertGreaterEqual(summary["win_rate_pct"], 0.0)
            self.assertLessEqual(summary["win_rate_pct"], 100.0)


class TestSmcApi(unittest.TestCase):
    """The SMC endpoints, over the anonymous DEMO dataset.

    Every result must carry the exact plain-text block, and the API must agree with
    it: a row that is not tradeable has to say "No Trade" and score zero.
    """

    LABELS = [
        "Symbol: ",
        "Confidence Score: ",
        "Trend Direction: ",
        "1D BOS Confirmed: ",
        "1D FVG Zone: ",
        "4H Refinement:",
        "Entry Price: ",
        "Stop Loss: ",
        "Take Profit: ",
        "Risk Reward Ratio: ",
        "Reasoning: ",
    ]

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def _scan(self) -> dict:
        resp = self.client.get("/api/smc/scan")
        self.assertEqual(resp.status_code, 200, resp.text)
        return resp.json()

    def test_scan_returns_demo_results(self):
        body = self._scan()
        self.assertTrue(body["demo"])
        self.assertGreater(body["scanned"], 0)
        self.assertTrue(body["results"])
        self.assertEqual(body["refinement_interval"], "4H")
        self.assertAlmostEqual(body["min_risk_reward"], 1.6, places=2)

    def test_every_result_carries_the_exact_plain_text_block(self):
        for row in self._scan()["results"]:
            lines = row["text"].split("\n")
            self.assertEqual(len(lines), 11, row["text"])
            for line, label in zip(lines, self.LABELS):
                self.assertTrue(line.startswith(label), f"{line!r} should start with {label!r}")
            # Nothing outside the structure: no JSON, no markdown fences.
            self.assertNotIn("{", row["text"])
            self.assertNotIn("```", row["text"])

    def test_the_text_agrees_with_the_structured_fields(self):
        for row in self._scan()["results"]:
            text = row["text"]
            self.assertIn(f"Symbol: {row['symbol']}", text)
            self.assertIn(f"Confidence Score: {row['confidence']:.0f}", text)
            self.assertIn(f"Trend Direction: {row['trend']}", text)
            self.assertIn(f"1D BOS Confirmed: {'Yes' if row['bos_confirmed'] else 'No'}", text)

            if row["tradeable"]:
                self.assertGreater(row["confidence"], 0)
                self.assertGreaterEqual(row["risk_reward"], 1.6 - 1e-9)
                self.assertNotIn("Reasoning: No Trade", text)
                self.assertIn(f"Entry Price: {row['entry']:.2f}", text)
                self.assertIn(f"Stop Loss: {row['stop']:.2f}", text)
                self.assertIn(f"Take Profit: {row['target']:.2f}", text)
                self.assertIn(f"Risk Reward Ratio: 1:{row['risk_reward']:.2f}", text)
            else:
                # A refused setup always scores zero and says "No Trade". It may
                # still report the levels it computed — a trade rejected only on
                # reward is more useful shown than hidden.
                self.assertEqual(row["confidence"], 0)
                self.assertTrue(row["reasoning"].startswith("No Trade"))
                if row["entry"] is None:
                    self.assertIn("Entry Price: n/a", text)
                else:
                    self.assertIn(f"Entry Price: {row['entry']:.2f}", text)

    def test_tradeable_rows_come_first(self):
        results = self._scan()["results"]
        flags = [r["tradeable"] for r in results]
        self.assertEqual(flags, sorted(flags, reverse=True), "tradeable setups rank first")

    def test_symbol_endpoint_returns_the_verdict_and_candles(self):
        body = self._scan()
        symbol = body["results"][0]["symbol"]

        resp = self.client.get(f"/api/smc/{symbol}")
        self.assertEqual(resp.status_code, 200, resp.text)
        detail = resp.json()
        self.assertEqual(detail["symbol"], symbol)
        self.assertEqual(detail["text"].split("\n")[0], f"Symbol: {symbol}")
        self.assertTrue(detail["daily_bars"], "the structure chart needs daily candles")
        for bar in detail["daily_bars"][:3]:
            self.assertLessEqual(bar["low"], bar["high"])
        self.assertIn("refinement_bars", detail)

    def test_scan_explains_the_data_state(self):
        """An empty screen must be able to say why it is empty."""
        status = self._scan()["data_status"]
        for key in ("ready", "daily_bars", "refinement_bars", "message", "market_day_note"):
            self.assertIn(key, status)
        self.assertTrue(status["ready"])
        self.assertTrue(status["message"])
        # The weekend question deserves a straight answer in the payload.
        self.assertIn("closed", status["market_day_note"])

    def test_health_reports_the_deployed_build(self):
        body = self.client.get("/api/health").json()
        self.assertEqual(body["status"], "ok")
        self.assertIn("version", body)
        self.assertIn("revision", body)
        self.assertIn("SMC", body["strategy"])

    def test_unknown_symbol_is_404(self):
        self.assertEqual(self.client.get("/api/smc/NOTATICKER").status_code, 404)

    def test_lowercase_symbol_is_accepted(self):
        symbol = self._scan()["results"][0]["symbol"].lower()
        self.assertEqual(self.client.get(f"/api/smc/{symbol}").status_code, 200)


if __name__ == "__main__":
    unittest.main()
