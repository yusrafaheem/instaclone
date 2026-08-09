import time
import unittest

import jwt

from app import auth, settings


class TestPasswordHashing(unittest.TestCase):
    def test_hash_and_verify_round_trip(self):
        h = auth.hash_password("correct horse battery staple")
        self.assertTrue(auth.verify_password("correct horse battery staple", h))

    def test_wrong_password_fails(self):
        h = auth.hash_password("correct horse battery staple")
        self.assertFalse(auth.verify_password("wrong password", h))

    def test_hashes_are_salted_differently(self):
        h1 = auth.hash_password("same password")
        h2 = auth.hash_password("same password")
        self.assertNotEqual(h1, h2)

    def test_malformed_hash_does_not_raise(self):
        self.assertFalse(auth.verify_password("anything", b"not-a-real-bcrypt-hash"))


class TestTokens(unittest.TestCase):
    def test_issue_and_verify_round_trip(self):
        token = auth.issue_token(42, "alice")
        payload = auth.verify_token(token)
        self.assertEqual(payload["sub"], 42)
        self.assertEqual(payload["username"], "alice")

    def test_tampered_token_is_rejected(self):
        token = auth.issue_token(1, "bob")
        tampered = token[:-1] + ("A" if token[-1] != "A" else "B")
        with self.assertRaises(auth.InvalidToken):
            auth.verify_token(tampered)

    def test_garbage_token_is_rejected(self):
        with self.assertRaises(auth.InvalidToken):
            auth.verify_token("not.a.jwt")

    def test_expired_token_is_rejected(self):
        payload = {
            "sub": 1,
            "username": "carol",
            "iat": int(time.time()) - 1000,
            "exp": int(time.time()) - 1,
        }
        expired = jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
        with self.assertRaises(auth.InvalidToken):
            auth.verify_token(expired)

    def test_token_signed_with_wrong_secret_is_rejected(self):
        payload = {
            "sub": 1,
            "username": "dave",
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600,
        }
        wrong = jwt.encode(payload, "not-the-real-secret", algorithm=settings.JWT_ALGORITHM)
        with self.assertRaises(auth.InvalidToken):
            auth.verify_token(wrong)


if __name__ == "__main__":
    unittest.main()
