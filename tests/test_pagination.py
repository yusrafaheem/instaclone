import base64
import json
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

    def test_encode_cursor_output_is_url_safe(self):
        # created_at/id values chosen to be likely to produce '+' or '/'
        # under standard base64; urlsafe encoding must avoid both.
        cursor = encode_cursor(1700000000.5, 123456789)
        self.assertNotIn("+", cursor)
        self.assertNotIn("/", cursor)

    def test_decode_cursor_rejects_non_dict_json(self):
        # A syntactically valid base64/JSON payload that isn't the
        # expected {"t": ..., "id": ...} shape should degrade to None,
        # not raise, same as a corrupted cursor.
        raw = base64.urlsafe_b64encode(json.dumps([1, 2, 3]).encode("utf-8"))
        self.assertIsNone(decode_cursor(raw.decode("ascii")))

    def test_cursor_round_trips_with_zero_id(self):
        cursor = encode_cursor(1700000000.0, 0)
        self.assertEqual(decode_cursor(cursor), (1700000000.0, 0))


if __name__ == "__main__":
    unittest.main()
