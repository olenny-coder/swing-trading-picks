"""Unit tests for encryption, hashing, JWT, and masking."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("SECRET_KEY", "unit-test-secret-key-longer-than-32-bytes-12345")

from app.core import security  # noqa: E402


class TestSecurity(unittest.TestCase):
    def test_encrypt_decrypt_roundtrip(self):
        token = security.encrypt_secret("my-api-key-123")
        self.assertNotIn("my-api-key-123", token)
        self.assertEqual(security.decrypt_secret(token), "my-api-key-123")

    def test_decrypt_garbage_raises(self):
        with self.assertRaises(ValueError):
            security.decrypt_secret("not-a-valid-fernet-token!!")

    def test_mask_key(self):
        masked = security.mask_key("AK1234567890ABCDEF1234")
        self.assertTrue(masked.startswith("AK"))
        self.assertTrue(masked.endswith("1234"))
        self.assertNotIn("ABCDEF", masked)

    def test_mask_short_key(self):
        self.assertEqual(security.mask_key("abc"), "***")

    def test_password_hash_verify(self):
        hashed = security.hash_password("s3cret")
        self.assertTrue(security.verify_password("s3cret", hashed))
        self.assertFalse(security.verify_password("wrong", hashed))

    def test_jwt_roundtrip(self):
        token = security.create_access_token("alice")
        payload = security.decode_access_token(token)
        self.assertEqual(payload["sub"], "alice")


if __name__ == "__main__":
    unittest.main()
