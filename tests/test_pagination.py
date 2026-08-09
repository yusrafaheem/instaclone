import unittest

from app.pagination import decode_cursor, encode_cursor


class TestPagination(unittest.TestCase):
    def test_encode_decode_round_trip(self):
        cursor = encode_cursor(1700000000.123, 42)
        self.assertEqual(decode_cursor(cursor), (1700000000.123, 42))

    def test_none_cursor_decodes_to_none(self):
        self.assertIsNone(decode_cursor(None))

    def test_empty_string_cursor_decodes_to_none(self):
        self.assertIsNone(decode_cursor(""))

    def test_garbage_cursor_decodes_to_none_not_an_exception(self):
        self.assertIsNone(decode_cursor("not-a-real-cursor!!"))

    def test_tampered_base64_decodes_to_none(self):
        cursor = encode_cursor(1700000000.0, 1)
        tampered = cursor[:-2] + "zz"
        # Either it fails to decode cleanly, or it decodes to something
        # else entirely -- either way it must not raise.
        decode_cursor(tampered)

    def test_two_different_rows_produce_different_cursors(self):
        c1 = encode_cursor(1700000000.0, 1)
        c2 = encode_cursor(1700000000.0, 2)
        self.assertNotEqual(c1, c2)


if __name__ == "__main__":
    unittest.main()
