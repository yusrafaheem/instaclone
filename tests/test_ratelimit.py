import time
import unittest

from app.ratelimit import RateLimiter


class TestRateLimiter(unittest.TestCase):
    def test_allows_requests_within_capacity(self):
        limiter = RateLimiter(requests_per_minute=60)
        for _ in range(60):
            self.assertTrue(limiter.allow("client-a"))

    def test_denies_once_capacity_is_exhausted(self):
        limiter = RateLimiter(requests_per_minute=5)
        for _ in range(5):
            self.assertTrue(limiter.allow("client-a"))
        self.assertFalse(limiter.allow("client-a"))

    def test_different_clients_have_independent_buckets(self):
        limiter = RateLimiter(requests_per_minute=1)
        self.assertTrue(limiter.allow("client-a"))
        self.assertFalse(limiter.allow("client-a"))
        self.assertTrue(limiter.allow("client-b"))

    def test_tokens_refill_over_time(self):
        limiter = RateLimiter(requests_per_minute=600)  # 10/sec
        self.assertTrue(limiter.allow("client-a"))
        # Exhaust remaining burst capacity.
        for _ in range(599):
            limiter.allow("client-a")
        self.assertFalse(limiter.allow("client-a"))
        time.sleep(0.2)  # ~2 tokens should have refilled
        self.assertTrue(limiter.allow("client-a"))

    def test_never_exceeds_capacity_even_after_long_idle(self):
        limiter = RateLimiter(requests_per_minute=10)
        limiter.allow("client-a")
        # Simulate a long idle period by rewriting the bucket's
        # last_refill far in the past, then confirm the burst is still
        # capped at the configured capacity rather than growing unbounded.
        bucket = limiter._buckets["client-a"]
        bucket.last_refill = time.time() - 10_000
        allowed = sum(1 for _ in range(50) if limiter.allow("client-a"))
        self.assertLessEqual(allowed, 10)

    def test_capacity_matches_requests_per_minute_argument(self):
        limiter = RateLimiter(requests_per_minute=42)
        self.assertEqual(limiter._capacity, 42.0)

    def test_partial_token_does_not_allow_request(self):
        limiter = RateLimiter(requests_per_minute=60)
        limiter.allow("client-a")  # creates the bucket
        bucket = limiter._buckets["client-a"]
        # Force the bucket into a state with less than one full token and
        # no time elapsed since the last refill, so the next call can only
        # be decided by the ">= 1.0" check itself.
        bucket.tokens = 0.5
        bucket.last_refill = time.time()
        self.assertFalse(limiter.allow("client-a"))


if __name__ == "__main__":
    unittest.main()
