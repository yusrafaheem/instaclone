import threading
import time
import unittest

from app.cache import TTLCache


class TestTTLCache(unittest.TestCase):
    def setUp(self):
        self.cache = TTLCache()

    def test_get_missing_key_returns_none(self):
        self.assertIsNone(self.cache.get("nope"))

    def test_set_then_get_round_trip(self):
        self.cache.set("k", {"a": 1}, ttl_seconds=10)
        self.assertEqual(self.cache.get("k"), {"a": 1})

    def test_expired_entry_returns_none(self):
        self.cache.set("k", "v", ttl_seconds=0.01)
        time.sleep(0.03)
        self.assertIsNone(self.cache.get("k"))

    def test_delete_removes_key(self):
        self.cache.set("k", "v", ttl_seconds=10)
        self.cache.delete("k")
        self.assertIsNone(self.cache.get("k"))

    def test_delete_missing_key_does_not_raise(self):
        self.cache.delete("does-not-exist")  # should not raise

    def test_delete_prefix_removes_matching_keys_only(self):
        self.cache.set("feed:1:a", "x", ttl_seconds=10)
        self.cache.set("feed:1:b", "y", ttl_seconds=10)
        self.cache.set("feed:2:a", "z", ttl_seconds=10)
        removed = self.cache.delete_prefix("feed:1:")
        self.assertEqual(removed, 2)
        self.assertIsNone(self.cache.get("feed:1:a"))
        self.assertIsNone(self.cache.get("feed:1:b"))
        self.assertEqual(self.cache.get("feed:2:a"), "z")

    def test_overwriting_a_key_updates_its_ttl(self):
        self.cache.set("k", "old", ttl_seconds=10)
        self.cache.set("k", "new", ttl_seconds=10)
        self.assertEqual(self.cache.get("k"), "new")

    def test_clear_all_empties_the_cache_regardless_of_ttl(self):
        self.cache.set("a", 1, ttl_seconds=1000)
        self.cache.set("b", 2, ttl_seconds=1000)
        self.cache.clear_all()
        self.assertIsNone(self.cache.get("a"))
        self.assertIsNone(self.cache.get("b"))

    def test_concurrent_writers_do_not_corrupt_state(self):
        def writer(n):
            for i in range(200):
                self.cache.set(f"k{n}", i, ttl_seconds=10)

        threads = [threading.Thread(target=writer, args=(n,)) for n in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        for n in range(8):
            self.assertEqual(self.cache.get(f"k{n}"), 199)


if __name__ == "__main__":
    unittest.main()
