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
os.environ["DATA_PROVIDER"] = "mock"
os.environ["ADMIN_USERNAME"] = "admin"
os.environ["ADMIN_PASSWORD"] = "testpass"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.services.demo_service import DEMO_ID_BASE  # noqa: E402


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
        for signal in data["signals"]:
            self.assertTrue(demo_service.is_demo_signal_id(signal["id"]))
        self.assertFalse(demo_service.is_demo_signal_id(1))

    def test_demo_signals_carry_the_blended_confidence(self):
        from app.services import demo_service

        demo_service.reset_cache()
        signals = demo_service.dataset()["signals"]
        self.assertTrue(signals)
        for signal in signals:
            components = signal["confidence_components"]
            self.assertIn("continuation", components)
            self.assertIn("reversal", components)
            self.assertIn("counter_impact", components)
            self.assertEqual(components["final"], signal["confidence"])


if __name__ == "__main__":
    unittest.main()
