"""Tests for the LLM research agent.

No network calls: the Groq client is replaced with a fake that returns canned
JSON, so the tests cover prompt construction, the strict validation of the
(untrusted) model reply, the confidence clamp, and the API surface.
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(_tmp, 'research.db')}"
os.environ["SECRET_KEY"] = "research-test-secret-key-longer-than-32-bytes-1234"
os.environ["DATA_PROVIDER"] = "mock"
os.environ["ADMIN_USERNAME"] = "admin"
os.environ["ADMIN_PASSWORD"] = "testpass"
os.environ.pop("GROQ_API_KEY", None)

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.providers.groq_provider import GroqCompletion  # noqa: E402
from app.services import research_service as rs  # noqa: E402


class FakeGroq:
    """Stand-in for GroqProvider that records the prompt it was given."""

    name = "fake-groq"

    def __init__(self, payload, model="fake-model"):
        self.payload = payload
        self.model = model
        self.calls: list[dict] = []

    def complete_json(self, *, system, user, max_tokens=700, temperature=0.2):
        self.calls.append({"system": system, "user": user, "max_tokens": max_tokens})
        return GroqCompletion(data=self.payload, model=self.model, usage={"total_tokens": 42})


class TestValidation(unittest.TestCase):
    def test_delta_is_clamped_to_the_configured_bound(self):
        high = rs.validate_annotation({"confidence_delta": 999}, 50.0, 15.0)
        low = rs.validate_annotation({"confidence_delta": -999}, 50.0, 15.0)
        self.assertEqual(high["confidence_delta"], 15.0)
        self.assertEqual(low["confidence_delta"], -15.0)

    def test_adjusted_confidence_stays_within_zero_and_hundred(self):
        top = rs.validate_annotation({"confidence_delta": 15}, 95.0, 15.0)
        bottom = rs.validate_annotation({"confidence_delta": -15}, 5.0, 15.0)
        self.assertEqual(top["adjusted_confidence"], 100.0)
        self.assertEqual(bottom["adjusted_confidence"], 0.0)

    def test_unknown_and_duplicate_flags_are_dropped(self):
        out = rs.validate_annotation(
            {"risk_flags": ["earnings_soon", "not_a_real_flag", "earnings_soon", "wide_stop"]},
            50.0,
            15.0,
        )
        self.assertEqual(out["risk_flags"], ["earnings_soon", "wide_stop"])

    def test_flag_list_is_capped(self):
        out = rs.validate_annotation({"risk_flags": list(rs.RISK_FLAGS)}, 50.0, 15.0)
        self.assertEqual(len(out["risk_flags"]), rs.MAX_FLAGS)

    def test_flags_accept_spaces_and_hyphens(self):
        out = rs.validate_annotation({"risk_flags": ["Earnings-Soon", "wide stop"]}, 50.0, 15.0)
        self.assertEqual(out["risk_flags"], ["earnings_soon", "wide_stop"])

    def test_sentiment_is_whitelisted(self):
        self.assertEqual(rs.validate_annotation({"sentiment": " BULLISH "}, 50.0, 15.0)["sentiment"], "bullish")
        self.assertEqual(rs.validate_annotation({"sentiment": "banana"}, 50.0, 15.0)["sentiment"], "neutral")
        self.assertEqual(rs.validate_annotation({}, 50.0, 15.0)["sentiment"], "neutral")

    def test_garbage_values_do_not_raise(self):
        for payload in (None, "nope", 42, [], {"risk_flags": None}, {"confidence_delta": "abc"}):
            out = rs.validate_annotation(payload, 50.0, 15.0)  # type: ignore[arg-type]
            self.assertIn(out["sentiment"], rs.SENTIMENTS)
            self.assertEqual(out["confidence_delta"], 0.0)
            self.assertEqual(out["adjusted_confidence"], 50.0)

    def test_nan_delta_is_neutralised(self):
        out = rs.validate_annotation({"confidence_delta": float("nan")}, 50.0, 15.0)
        self.assertEqual(out["confidence_delta"], 0.0)

    def test_rationale_is_flattened_and_truncated(self):
        out = rs.validate_annotation(
            {"rationale": "line one\nline two\t\t" + "x" * 500}, 50.0, 15.0
        )
        self.assertNotIn("\n", out["rationale"])
        self.assertNotIn("\t", out["rationale"])
        self.assertLessEqual(len(out["rationale"]), rs.MAX_RATIONALE)

    def test_supports_setup_follows_the_delta_sign(self):
        self.assertTrue(rs.validate_annotation({"confidence_delta": 5}, 50.0, 15.0)["supports_setup"])
        self.assertFalse(rs.validate_annotation({"confidence_delta": -5}, 50.0, 15.0)["supports_setup"])

    def test_media_counter_impact_is_non_negative_and_bounded(self):
        out = rs.validate_annotation({"counter_impact": 99}, 50.0, 15.0)
        self.assertEqual(out["counter_impact"], 15.0)
        # A negative value is a magnitude, so it is normalised rather than trusted.
        self.assertEqual(rs.validate_annotation({"counter_impact": -6}, 50.0, 15.0)["counter_impact"], 6.0)
        self.assertEqual(rs.validate_annotation({}, 50.0, 15.0)["counter_impact"], 0.0)
        self.assertEqual(
            rs.validate_annotation({"counter_impact": "lots"}, 50.0, 15.0)["counter_impact"], 0.0
        )
        self.assertEqual(
            rs.validate_annotation({"counter_impact": float("nan")}, 50.0, 15.0)["counter_impact"],
            0.0,
        )

    def test_system_prompt_requests_the_counter_impact(self):
        self.assertIn("counter_impact", rs.SYSTEM_PROMPT)
        self.assertIn("against", rs.SYSTEM_PROMPT.lower())

    def test_system_prompt_lists_only_known_flags(self):
        self.assertIn("JSON only", rs.SYSTEM_PROMPT)
        for flag in rs.RISK_FLAGS:
            self.assertIn(flag, rs.SYSTEM_PROMPT)
        self.assertIn("Do not invent", rs.SYSTEM_PROMPT)


class TestAgentWithFakeGroq(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.client.__enter__()  # seed the demo DB so a real Signal exists
        from app.database import SessionLocal

        cls.db = SessionLocal()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()
        cls.client.__exit__(None, None, None)

    def _a_signal(self):
        from app.models import Signal

        return self.db.query(Signal).order_by(Signal.confidence.desc()).first()

    def test_brief_contains_the_decision_inputs(self):
        signal = self._a_signal()
        self.assertIsNotNone(signal, "expected seeded signals")
        brief = rs.build_brief(self.db, signal)
        for expected in ("TICKER:", "SETUP:", signal.ticker, str(signal.setup), "LEVELS:", "CONTEXT:"):
            self.assertIn(expected, brief)
        self.assertLess(len(brief), 2000, "brief must stay small for the free tier")

    def test_annotate_signal_uses_the_fake_provider(self):
        signal = self._a_signal()
        provider = FakeGroq(
            {
                "sentiment": "bearish",
                "risk_flags": ["earnings_soon", "extended_move"],
                "confidence_delta": -8,
                "rationale": "Momentum is stretched into earnings.",
            }
        )
        annotation = rs.annotate_signal(self.db, signal, provider)  # type: ignore[arg-type]

        self.assertEqual(len(provider.calls), 1)
        self.assertEqual(annotation["sentiment"], "bearish")
        self.assertEqual(annotation["risk_flags"], ["earnings_soon", "extended_move"])
        self.assertEqual(annotation["confidence_delta"], -8.0)
        self.assertEqual(
            annotation["adjusted_confidence"], round(signal.confidence - 8.0, 1)
        )
        self.assertEqual(annotation["base_confidence"], round(signal.confidence, 1))
        self.assertEqual(annotation["model"], "fake-model")
        self.assertTrue(annotation["created_at"].endswith("Z"))

    def test_annotation_is_stored_on_the_signal(self):
        signal = self._a_signal()
        provider = FakeGroq({"sentiment": "neutral", "risk_flags": [], "confidence_delta": 3, "rationale": "ok"})
        signal.annotation = rs.annotate_signal(self.db, signal, provider)  # type: ignore[arg-type]
        self.db.add(signal)
        self.db.commit()
        self.db.refresh(signal)
        self.assertIsNotNone(signal.annotation)
        self.assertEqual(signal.annotation["confidence_delta"], 3.0)

    def test_resolve_provider_returns_none_without_a_key(self):
        self.assertIsNone(rs.resolve_provider(self.db, None))


class TestResearchAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def _auth_headers(self) -> dict:
        resp = self.client.post("/api/auth/login", json={"username": "admin", "password": "testpass"})
        self.assertEqual(resp.status_code, 200, resp.text)
        return {"Authorization": f"Bearer {resp.json()['access_token']}"}

    def test_status_is_public(self):
        resp = self.client.get("/api/research/status")
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertIn("configured", body)
        self.assertFalse(body["configured"], "no GROQ_API_KEY should be set in tests")
        self.assertIn("openai/gpt-oss-120b", body["model"])
        self.assertIn("risk_flags", body)

    def test_run_requires_auth(self):
        self.assertEqual(self.client.post("/api/research/run", json={}).status_code, 401)

    def test_run_reports_missing_key_rather_than_failing(self):
        resp = self.client.post("/api/research/run", json={}, headers=self._auth_headers())
        self.assertEqual(resp.status_code, 409, resp.text)
        self.assertIn("Groq API key", resp.json()["detail"])

    def test_clear_requires_auth(self):
        self.assertEqual(self.client.delete("/api/research").status_code, 401)

    def test_signal_payload_exposes_an_annotation_field(self):
        listing = self.client.get("/api/signals/daily").json()
        self.assertTrue(listing["signals"])
        self.assertIn("annotation", listing["signals"][0])


class TestGroqWireFormat(unittest.TestCase):
    """The Groq client is exercised against a fake httpx transport."""

    def _patch(self, responses):
        import json as _json

        queue = list(responses)
        calls: list[dict] = []

        class _Resp:
            def __init__(self, status_code, payload=None, text="", headers=None):
                self.status_code = status_code
                self._payload = payload
                self.text = text or (_json.dumps(payload) if payload is not None else "")
                self.headers = headers or {}

            def json(self):
                if self._payload is None:
                    raise ValueError("not json")
                return self._payload

        class _Client:
            def __init__(self, **_kw):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *_a):
                return False

            def post(self, url, json=None, headers=None):
                calls.append({"url": url, "json": json, "headers": headers})
                if queue:
                    return queue.pop(0)
                return _Resp(500, text="queue exhausted")

        return _Client, calls, _Resp

    def _run(self, responses, **kwargs):
        from unittest.mock import patch

        from app.providers.groq_provider import GroqProvider

        client_cls, calls, _ = self._patch(responses)
        provider = GroqProvider("test-key", model="test-model", max_retries=kwargs.pop("max_retries", 0))
        with patch("app.providers.groq_provider.httpx.Client", client_cls), patch(
            "app.providers.groq_provider.time.sleep"
        ):
            result = provider.complete_json(system="sys", user="usr", **kwargs)
        return result, calls

    def test_posts_openai_compatible_request_with_json_mode(self):
        ok = {
            "model": "test-model",
            "choices": [{"message": {"content": '{"sentiment":"bullish"}'}}],
            "usage": {"total_tokens": 7},
        }
        result, calls = self._run([self._Resp_ok(ok)])
        self.assertEqual(result.data, {"sentiment": "bullish"})
        self.assertEqual(result.model, "test-model")
        self.assertEqual(result.usage, {"total_tokens": 7})

        call = calls[0]
        self.assertTrue(call["url"].endswith("/chat/completions"))
        self.assertIn("api.groq.com", call["url"])
        self.assertEqual(call["headers"]["Authorization"], "Bearer test-key")
        self.assertEqual(call["json"]["response_format"], {"type": "json_object"})
        self.assertEqual(call["json"]["model"], "test-model")
        self.assertEqual(call["json"]["messages"][0]["role"], "system")
        self.assertEqual(call["json"]["messages"][1]["content"], "usr")

    def _Resp_ok(self, payload):
        _, _, Resp = self._patch([])
        return Resp(200, payload)

    def test_http_error_surfaces_the_api_message(self):
        from app.providers.groq_provider import GroqError

        _, _, Resp = self._patch([])
        bad = Resp(400, {"error": {"message": "model not found"}})
        with self.assertRaises(GroqError) as ctx:
            self._run([bad])
        self.assertIn("model not found", str(ctx.exception))

    def test_rate_limit_is_retried_then_succeeds(self):
        _, _, Resp = self._patch([])
        good = Resp(
            200,
            {
                "model": "test-model",
                "choices": [{"message": {"content": '{"ok":true}'}}],
            },
        )
        result, calls = self._run(
            [Resp(429, headers={"retry-after": "0"}), good], max_retries=2
        )
        self.assertEqual(result.data, {"ok": True})
        self.assertEqual(len(calls), 2, "expected one retry after the 429")

    def test_non_json_reply_raises(self):
        from app.providers.groq_provider import GroqError

        _, _, Resp = self._patch([])
        resp = Resp(200, {"choices": [{"message": {"content": "not json at all"}}]})
        with self.assertRaises(GroqError):
            self._run([resp])

    def test_missing_api_key_is_rejected(self):
        from app.providers.groq_provider import GroqError, GroqProvider

        with self.assertRaises(GroqError):
            GroqProvider("")


if __name__ == "__main__":
    unittest.main()
