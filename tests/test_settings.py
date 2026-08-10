"""Tests for app/settings.py. Config is read from environment variables
at *import* time, so these tests patch os.environ and importlib.reload
the module to exercise that path, then always reload once more with the
real environment in tearDown -- forgetting that would leak one test's
patched values into every test that runs after it in the same process,
since other modules hold a reference to this same module object."""

import importlib
import os
import unittest
from pathlib import Path
from unittest import mock

from app import settings


class TestSettings(unittest.TestCase):
    def tearDown(self):
        importlib.reload(settings)

    def test_default_db_path_is_under_base_dir(self):
        importlib.reload(settings)
        self.assertTrue(settings.DB_PATH.endswith("instaclone.db"))
        self.assertTrue(Path(settings.DB_PATH).is_absolute())

    def test_db_path_env_var_override(self):
        with mock.patch.dict(os.environ, {"INSTACLONE_DB_PATH": "/tmp/custom.db"}):
            importlib.reload(settings)
            self.assertEqual(settings.DB_PATH, "/tmp/custom.db")

    def test_jwt_secret_env_var_override(self):
        with mock.patch.dict(os.environ, {"INSTACLONE_JWT_SECRET": "super-secret"}):
            importlib.reload(settings)
            self.assertEqual(settings.JWT_SECRET, "super-secret")

    def test_jwt_ttl_defaults_to_seven_days(self):
        importlib.reload(settings)
        self.assertEqual(settings.JWT_TTL_SECONDS, 60 * 60 * 24 * 7)

    def test_server_port_env_var_override(self):
        with mock.patch.dict(os.environ, {"INSTACLONE_PORT": "9999"}):
            importlib.reload(settings)
            self.assertEqual(settings.SERVER_PORT, 9999)

    def test_server_port_defaults_to_8000_when_unset(self):
        env = dict(os.environ)
        env.pop("INSTACLONE_PORT", None)
        with mock.patch.dict(os.environ, env, clear=True):
            importlib.reload(settings)
            self.assertEqual(settings.SERVER_PORT, 8000)


if __name__ == "__main__":
    unittest.main()
