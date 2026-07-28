import os
import subprocess
import sys

from django.test import SimpleTestCase


class SecretKeySettingsTests(SimpleTestCase):
    def import_production_settings(self, secret_key: str | None) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["DJANGO_SETTINGS_MODULE"] = "config.settings"
        env["DJANGO_DEBUG"] = "False"
        if secret_key is None:
            env.pop("DJANGO_SECRET_KEY", None)
        else:
            env["DJANGO_SECRET_KEY"] = secret_key

        return subprocess.run(
            [sys.executable, "-c", "import config.settings"],
            capture_output=True,
            check=False,
            env=env,
            text=True,
        )

    def test_missing_secret_key_is_rejected_in_production(self):
        result = self.import_production_settings(None)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "DJANGO_SECRET_KEY must be set to a non-default value in production.",
            result.stderr,
        )

    def test_empty_secret_key_is_rejected_in_production(self):
        result = self.import_production_settings("")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "DJANGO_SECRET_KEY must be set to a non-default value in production.",
            result.stderr,
        )

    def test_default_secret_key_is_rejected_in_production(self):
        result = self.import_production_settings("django-insecure-fallback-key")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "DJANGO_SECRET_KEY must be set to a non-default value in production.",
            result.stderr,
        )

    def test_custom_secret_key_is_accepted_in_production(self):
        result = self.import_production_settings("custom-production-secret")

        self.assertEqual(result.returncode, 0, result.stderr)
