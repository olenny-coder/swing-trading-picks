"""End-to-end API tests using the MOCK provider and a throwaway SQLite DB."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(_tmp, 'test.db')}"
os.environ["SECRET_KEY"] = "api-test-secret-key-that-is-longer-than-32-bytes-123456"
os.environ["DATA_PROVIDER"] = "mock"
os.environ["ADMIN_USERNAME"] = "admin"
os.environ["ADMIN_PASSWORD"] = "testpass"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


class TestAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.client.__enter__()  # run lifespan (init db, seed demo, scheduler)

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def _auth_headers(self) -> dict:
        resp = self.client.post("/api/auth/login", json={"username": "admin", "password": "testpass"})
        self.assertEqual(resp.status_code, 200, resp.text)
        token = resp.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

    def test_health(self):
        resp = self.client.get("/api/health")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "ok")

    def test_login_rejects_bad_password(self):
        resp = self.client.post("/api/auth/login", json={"username": "admin", "password": "nope"})
        self.assertEqual(resp.status_code, 401)

    def test_settings_requires_auth(self):
        self.assertEqual(self.client.get("/api/settings").status_code, 401)

    def test_refresh_requires_auth(self):
        self.assertEqual(self.client.post("/api/refresh").status_code, 401)

    def test_public_read_without_auth(self):
        # Read-only endpoints must be viewable without logging in.
        for path in ("/api/signals/daily", "/api/signals", "/api/signals/summary", "/api/macro/dashboard"):
            resp = self.client.get(path)
            self.assertEqual(resp.status_code, 200, f"{path} -> {resp.status_code}")

    def test_public_signal_detail_without_auth(self):
        listing = self.client.get("/api/signals/daily").json()
        self.assertTrue(listing["signals"], "expected seeded signals")
        sig_id = listing["signals"][0]["id"]
        resp = self.client.get(f"/api/signals/{sig_id}")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("bars", resp.json())

    def test_settings_roundtrip_masked(self):
        h = self._auth_headers()
        resp = self.client.get("/api/settings", headers=h)
        self.assertEqual(resp.status_code, 200)

        # Save an Alpaca credential; response must be masked (never plaintext).
        put = self.client.put(
            "/api/settings/credentials/alpaca",
            json={"provider": "alpaca", "api_key": "AK-SECRET-KEY-VALUE-1234", "secret_key": "secret-secret", "is_paper": True},
            headers=h,
        )
        self.assertEqual(put.status_code, 200, put.text)
        body = put.json()
        self.assertNotIn("AK-SECRET-KEY-VALUE-1234", str(body))
        self.assertTrue(body["key_masked"].startswith("AK"))
        self.assertTrue(body["key_masked"].endswith("1234"))
        self.assertTrue(body["has_key"])

    def test_test_connection_no_credentials(self):
        h = self._auth_headers()
        resp = self.client.post("/api/settings/test", json={"provider": "finnhub"}, headers=h)
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.json()["ok"])

    def test_daily_shortlist(self):
        h = self._auth_headers()
        resp = self.client.get("/api/signals/daily", headers=h)
        self.assertEqual(resp.status_code, 200, resp.text)
        data = resp.json()
        self.assertGreater(data["total"], 0)
        self.assertLessEqual(len(data["signals"]), 20)
        # Summary present.
        self.assertIn("summary", data)
        self.assertIn("regime", data["summary"])

    def test_signals_filter_by_type(self):
        h = self._auth_headers()
        resp = self.client.get("/api/signals", params={"type": "PUT"}, headers=h)
        self.assertEqual(resp.status_code, 200)
        for s in resp.json()["signals"]:
            self.assertEqual(s["type"], "PUT")

    def test_macro_dashboard(self):
        h = self._auth_headers()
        resp = self.client.get("/api/macro/dashboard", headers=h)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("snapshot", resp.json())

    def test_signal_detail(self):
        h = self._auth_headers()
        listing = self.client.get("/api/signals/daily", headers=h).json()
        self.assertTrue(listing["signals"], "expected seeded signals")
        sig_id = listing["signals"][0]["id"]
        resp = self.client.get(f"/api/signals/{sig_id}", headers=h)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("bars", resp.json())
        self.assertIn("indicators", resp.json())

    def test_refresh_endpoint(self):
        h = self._auth_headers()
        resp = self.client.post("/api/refresh", headers=h)
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertTrue(resp.json()["started"] or resp.json()["running"])

        import time

        deadline = time.time() + 180
        result = None
        while time.time() < deadline:
            state = self.client.get("/api/refresh/status", headers=h).json()
            if not state["running"]:
                self.assertIsNone(state["error"], state.get("error"))
                result = state["result"]
                break
            time.sleep(1)
        self.assertIsNotNone(result, "refresh did not finish in time")
        self.assertGreater(result["bars"], 0)
        self.assertGreater(result["signals"]["total"], 0)


if __name__ == "__main__":
    unittest.main()
