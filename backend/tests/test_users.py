"""User-management tests: admins add/disable/promote authorized users.

Covers the authorization boundary (admin vs authorized member vs guest) and the
lock-out guards (you cannot delete yourself, and the last active administrator
cannot be demoted, disabled or deleted).
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(_tmp, 'users.db')}"
os.environ["SECRET_KEY"] = "users-test-secret-key-longer-than-32-bytes-1234"
os.environ["DATA_PROVIDER"] = "mock"
os.environ["ADMIN_USERNAME"] = "admin"
os.environ["ADMIN_PASSWORD"] = "testpass"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

_counter = {"n": 0}


def _unique(prefix: str) -> str:
    _counter["n"] += 1
    return f"{prefix}{_counter['n']}"


class TestUserManagement(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def setUp(self):
        """Reset to exactly one active admin so each test is independent.

        Several tests deliberately demote, disable or delete accounts, which
        would otherwise leak into whichever test runs next.
        """
        from app.core import security
        from app.database import SessionLocal
        from app.models import ApiCredential, User

        db = SessionLocal()
        try:
            db.query(ApiCredential).delete()
            db.query(User).delete()
            db.add(
                User(
                    username="admin",
                    hashed_password=security.hash_password("testpass"),
                    is_active=True,
                    is_admin=True,
                )
            )
            db.commit()
        finally:
            db.close()

    # -- helpers -----------------------------------------------------------
    def _login(self, username: str, password: str):
        return self.client.post(
            "/api/auth/login", json={"username": username, "password": password}
        )

    def _admin_headers(self) -> dict:
        resp = self._login("admin", "testpass")
        self.assertEqual(resp.status_code, 200, resp.text)
        return {"Authorization": f"Bearer {resp.json()['access_token']}"}

    def _make_user(self, password: str = "memberpass123", is_admin: bool = False) -> str:
        username = _unique("member")
        resp = self.client.post(
            "/api/users",
            json={"username": username, "password": password, "is_admin": is_admin},
            headers=self._admin_headers(),
        )
        self.assertEqual(resp.status_code, 201, resp.text)
        return username

    # -- the bootstrap admin ----------------------------------------------
    def test_bootstrap_admin_is_an_admin(self):
        body = self.client.get("/api/auth/me", headers=self._admin_headers()).json()
        self.assertEqual(body["username"], "admin")
        self.assertTrue(body["is_admin"])
        self.assertTrue(body["is_active"])

    # -- authorization boundary -------------------------------------------
    def test_user_management_requires_authentication(self):
        self.assertEqual(self.client.get("/api/users").status_code, 401)

    def test_guest_cannot_create_users(self):
        resp = self.client.post(
            "/api/users", json={"username": "sneaky", "password": "password123"}
        )
        self.assertEqual(resp.status_code, 401)

    def test_authorized_member_cannot_manage_users(self):
        username = self._make_user()
        headers = {
            "Authorization": f"Bearer {self._login(username, 'memberpass123').json()['access_token']}"
        }
        self.assertEqual(self.client.get("/api/users", headers=headers).status_code, 403)
        resp = self.client.post(
            "/api/users",
            json={"username": "another", "password": "password123"},
            headers=headers,
        )
        self.assertEqual(resp.status_code, 403)

    def test_member_cannot_reach_admin_only_endpoints(self):
        username = self._make_user()
        headers = {
            "Authorization": f"Bearer {self._login(username, 'memberpass123').json()['access_token']}"
        }
        self.assertEqual(self.client.get("/api/settings", headers=headers).status_code, 403)
        self.assertEqual(self.client.post("/api/refresh", headers=headers).status_code, 403)

    # -- adding authorized users ------------------------------------------
    def test_admin_creates_an_authorized_user_who_can_sign_in(self):
        username = self._make_user()
        resp = self._login(username, "memberpass123")
        self.assertEqual(resp.status_code, 200, resp.text)

    def test_authorized_user_sees_live_data_not_the_demo(self):
        """The whole point: an added user gets the real shortlist."""
        username = self._make_user()
        headers = {
            "Authorization": f"Bearer {self._login(username, 'memberpass123').json()['access_token']}"
        }
        body = self.client.get("/api/signals/daily", headers=headers).json()
        self.assertFalse(body["demo"], "an authorized user must see live data")

        guest = self.client.get("/api/signals/daily").json()
        self.assertTrue(guest["demo"], "a guest must still see the demo")

    def test_created_user_appears_in_the_list(self):
        username = self._make_user()
        listing = self.client.get("/api/users", headers=self._admin_headers()).json()
        usernames = [u["username"] for u in listing]
        self.assertIn(username, usernames)
        self.assertIn("admin", usernames)

    def test_duplicate_username_is_rejected(self):
        username = self._make_user()
        resp = self.client.post(
            "/api/users",
            json={"username": username, "password": "password123"},
            headers=self._admin_headers(),
        )
        self.assertEqual(resp.status_code, 409, resp.text)

    def test_duplicate_username_is_rejected_case_insensitively(self):
        username = self._make_user()
        resp = self.client.post(
            "/api/users",
            json={"username": username.upper(), "password": "password123"},
            headers=self._admin_headers(),
        )
        self.assertEqual(resp.status_code, 409, resp.text)

    def test_short_password_is_rejected(self):
        resp = self.client.post(
            "/api/users",
            json={"username": _unique("weak"), "password": "short"},
            headers=self._admin_headers(),
        )
        self.assertEqual(resp.status_code, 422, resp.text)

    def test_invalid_username_is_rejected(self):
        for bad in ("ab", "has space", "has/slash", "x" * 70):
            resp = self.client.post(
                "/api/users",
                json={"username": bad, "password": "password123"},
                headers=self._admin_headers(),
            )
            self.assertEqual(resp.status_code, 422, f"{bad!r} should be rejected")

    # -- lifecycle ---------------------------------------------------------
    def test_admin_can_disable_and_reenable_a_user(self):
        username = self._make_user()
        user_id = self._find(username)["id"]

        resp = self.client.patch(
            f"/api/users/{user_id}", json={"is_active": False}, headers=self._admin_headers()
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertFalse(resp.json()["is_active"])

        login = self._login(username, "memberpass123")
        self.assertEqual(login.status_code, 401)
        self.assertIn("disabled", login.json()["detail"].lower())

        self.client.patch(
            f"/api/users/{user_id}", json={"is_active": True}, headers=self._admin_headers()
        )
        self.assertEqual(self._login(username, "memberpass123").status_code, 200)

    def test_disabled_users_existing_token_stops_working(self):
        username = self._make_user()
        user_id = self._find(username)["id"]
        stale = {
            "Authorization": f"Bearer {self._login(username, 'memberpass123').json()['access_token']}"
        }
        self.assertFalse(self.client.get("/api/signals/daily", headers=stale).json()["demo"])
        self.client.patch(
            f"/api/users/{user_id}", json={"is_active": False}, headers=self._admin_headers()
        )
        # The token no longer resolves, so the caller falls back to the demo.
        self.assertTrue(self.client.get("/api/signals/daily", headers=stale).json()["demo"])

    def test_admin_can_reset_a_password(self):
        username = self._make_user()
        user_id = self._find(username)["id"]
        resp = self.client.patch(
            f"/api/users/{user_id}",
            json={"password": "brandnewpass456"},
            headers=self._admin_headers(),
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(self._login(username, "memberpass123").status_code, 401)
        self.assertEqual(self._login(username, "brandnewpass456").status_code, 200)

    def test_admin_can_promote_a_member(self):
        username = self._make_user()
        user_id = self._find(username)["id"]
        self.client.patch(
            f"/api/users/{user_id}", json={"is_admin": True}, headers=self._admin_headers()
        )
        headers = {
            "Authorization": f"Bearer {self._login(username, 'memberpass123').json()['access_token']}"
        }
        self.assertEqual(self.client.get("/api/users", headers=headers).status_code, 200)

    def test_admin_can_delete_a_user(self):
        username = self._make_user()
        user_id = self._find(username)["id"]
        resp = self.client.delete(f"/api/users/{user_id}", headers=self._admin_headers())
        self.assertEqual(resp.status_code, 204, resp.text)
        self.assertEqual(self._login(username, "memberpass123").status_code, 401)
        self.assertIsNone(self._find(username))

    # -- lock-out guards ---------------------------------------------------
    def test_admin_cannot_delete_their_own_account(self):
        me = self.client.get("/api/auth/me", headers=self._admin_headers()).json()
        resp = self.client.delete(f"/api/users/{me['id']}", headers=self._admin_headers())
        self.assertEqual(resp.status_code, 409, resp.text)

    def test_last_active_admin_cannot_be_demoted(self):
        me = self.client.get("/api/auth/me", headers=self._admin_headers()).json()
        # No other admin exists in a fresh database.
        resp = self.client.patch(
            f"/api/users/{me['id']}", json={"is_admin": False}, headers=self._admin_headers()
        )
        self.assertEqual(resp.status_code, 409, resp.text)

    def test_last_active_admin_cannot_be_disabled(self):
        me = self.client.get("/api/auth/me", headers=self._admin_headers()).json()
        resp = self.client.patch(
            f"/api/users/{me['id']}", json={"is_active": False}, headers=self._admin_headers()
        )
        self.assertEqual(resp.status_code, 409, resp.text)

    def test_unknown_user_id_is_a_404(self):
        self.assertEqual(
            self.client.patch(
                "/api/users/999999", json={"is_active": False}, headers=self._admin_headers()
            ).status_code,
            404,
        )

    # -- helpers -----------------------------------------------------------
    def _find(self, username: str):
        listing = self.client.get("/api/users", headers=self._admin_headers()).json()
        return next((u for u in listing if u["username"] == username), None)


if __name__ == "__main__":
    unittest.main()
