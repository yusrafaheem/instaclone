import io
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from app import images, settings


def _jpeg_bytes(size=(400, 400), color=(200, 100, 50)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "JPEG")
    return buf.getvalue()


class TestSaveUpload(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._orig_media_dir = settings.MEDIA_DIR
        self._orig_uploads_dir = settings.UPLOADS_DIR
        self._orig_thumbs_dir = settings.THUMBS_DIR
        settings.MEDIA_DIR = Path(self._tmp.name)
        settings.UPLOADS_DIR = settings.MEDIA_DIR / "uploads"
        settings.THUMBS_DIR = settings.MEDIA_DIR / "thumbs"

    def tearDown(self):
        settings.MEDIA_DIR = self._orig_media_dir
        settings.UPLOADS_DIR = self._orig_uploads_dir
        settings.THUMBS_DIR = self._orig_thumbs_dir
        self._tmp.cleanup()

    def test_valid_image_produces_both_files_on_disk(self):
        image_path, thumb_path = images.save_upload(_jpeg_bytes(), user_id=1)
        self.assertTrue((settings.MEDIA_DIR / image_path).exists())
        self.assertTrue((settings.MEDIA_DIR / thumb_path).exists())

    def test_thumbnail_is_within_configured_bounds(self):
        image_path, thumb_path = images.save_upload(_jpeg_bytes(size=(2000, 1000)), user_id=1)
        with Image.open(settings.MEDIA_DIR / thumb_path) as thumb:
            self.assertLessEqual(thumb.width, settings.THUMBNAIL_SIZE[0])
            self.assertLessEqual(thumb.height, settings.THUMBNAIL_SIZE[1])

    def test_full_size_image_is_not_upscaled_or_distorted(self):
        image_path, _ = images.save_upload(_jpeg_bytes(size=(400, 300)), user_id=1)
        with Image.open(settings.MEDIA_DIR / image_path) as full:
            self.assertEqual(full.size, (400, 300))

    def test_non_image_bytes_raise_invalid_image_error(self):
        with self.assertRaises(images.InvalidImageError):
            images.save_upload(b"this is definitely not an image", user_id=1)

    def test_oversized_upload_is_rejected_before_decoding(self):
        huge = b"x" * (settings.MAX_UPLOAD_BYTES + 1)
        with self.assertRaises(images.InvalidImageError):
            images.save_upload(huge, user_id=1)

    def test_non_rgb_source_is_normalized_to_rgb_jpeg(self):
        buf = io.BytesIO()
        Image.new("RGBA", (100, 100), (10, 20, 30, 128)).save(buf, "PNG")
        image_path, _ = images.save_upload(buf.getvalue(), user_id=1)
        with Image.open(settings.MEDIA_DIR / image_path) as saved:
            self.assertEqual(saved.mode, "RGB")

    def test_two_uploads_from_the_same_user_get_distinct_filenames(self):
        path_a, _ = images.save_upload(_jpeg_bytes(), user_id=7)
        path_b, _ = images.save_upload(_jpeg_bytes(), user_id=7)
        self.assertNotEqual(path_a, path_b)


if __name__ == "__main__":
    unittest.main()
