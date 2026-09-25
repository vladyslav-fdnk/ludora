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


class HttpsProxySettingsTests(SimpleTestCase):
    def read_settings(self, behind_proxy: str | None) -> str:
        env = os.environ.copy()
        env["DJANGO_SETTINGS_MODULE"] = "config.settings"
        env["DJANGO_SECRET_KEY"] = "custom-production-secret"
        if behind_proxy is None:
            env.pop("DJANGO_BEHIND_HTTPS_PROXY", None)
        else:
            env["DJANGO_BEHIND_HTTPS_PROXY"] = behind_proxy

        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "from config import settings as s; "
                "print(getattr(s, 'SECURE_PROXY_SSL_HEADER', None), "
                "getattr(s, 'SESSION_COOKIE_SECURE', False), "
                "getattr(s, 'CSRF_COOKIE_SECURE', False))",
            ],
            capture_output=True,
            check=True,
            env=env,
            text=True,
        )
        return result.stdout.strip()

    def test_proxy_headers_are_not_trusted_by_default(self):
        self.assertEqual(self.read_settings(None), "None False False")

    def test_https_proxy_mode_trusts_forwarded_proto_and_secures_cookies(self):
        self.assertEqual(
            self.read_settings("True"),
            "('HTTP_X_FORWARDED_PROTO', 'https') True True",
        )
