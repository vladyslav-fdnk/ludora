from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

User = get_user_model()


class RegisterTests(APITestCase):
    def test_registration_requires_only_email_and_password(self):
        response = self.client.post(
            "/api/auth/register/",
            {"email": "vlad@test.com", "password": "password123"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(User.objects.filter(email="vlad@test.com").exists())
        self.assertNotIn("username", response.data)

    def test_duplicate_email_returns_bad_request(self):
        User.objects.create_user(email="vlad@test.com", password="password123")

        response = self.client.post(
            "/api/auth/register/",
            {"email": "vlad@test.com", "password": "password123"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_case_insensitive_duplicate_email_returns_bad_request(self):
        User.objects.create_user(email="Vlad@Test.com", password="password123")

        response = self.client.post(
            "/api/auth/register/",
            {"email": "vlad@test.com", "password": "password123"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class LoginTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="vlad@test.com",
            password="password123",
        )

    def test_user_can_login(self):
        response = self.client.post(
            "/api/auth/login/",
            {"email": "vlad@test.com", "password": "password123"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)

    def test_login_rejects_invalid_password(self):
        response = self.client.post(
            "/api/auth/login/",
            {"email": "vlad@test.com", "password": "incorrect-password"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_login_rejects_unknown_email(self):
        response = self.client.post(
            "/api/auth/login/",
            {"email": "unknown@test.com", "password": "password123"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_refresh_returns_access_token(self):
        refresh = RefreshToken.for_user(self.user)

        response = self.client.post(
            "/api/auth/refresh/",
            {"refresh": str(refresh)},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)

    def test_existing_protected_endpoint_accepts_jwt(self):
        access = RefreshToken.for_user(self.user).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

        response = self.client.get("/api/orders/my/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)


class MeTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="vlad@test.com",
            password="password123",
        )

    def test_authenticated_user_can_get_profile(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.get("/api/auth/me/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data,
            {
                "id": self.user.id,
                "email": "vlad@test.com",
                "first_name": "",
                "last_name": "",
                "telegram_username": "",
                "telegram_language_code": "",
                "date_joined": response.data["date_joined"],
            },
        )
        self.assertNotIn("username", response.data)

    def test_anonymous_user_cannot_get_profile(self):
        response = self.client.get("/api/auth/me/")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class OpenAPITests(APITestCase):
    def test_authentication_schemas_use_email_and_password(self):
        response = self.client.get("/api/schema/", HTTP_ACCEPT="application/json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for route in ("/api/auth/login/", "/api/auth/register/"):
            operation = response.data["paths"][route]["post"]
            request_schema = operation["requestBody"]["content"]["application/json"][
                "schema"
            ]
            component_name = request_schema["$ref"].rsplit("/", maxsplit=1)[-1]
            properties = response.data["components"]["schemas"][component_name][
                "properties"
            ]

            self.assertIn("email", properties)
            self.assertIn("password", properties)
            self.assertNotIn("username", properties)


@override_settings(BOT_INTERNAL_SECRET="test-placeholder-secret")
class TelegramAuthenticationTests(APITestCase):
    url = "/api/auth/telegram/"
    headers = {"HTTP_X_BOT_INTERNAL_SECRET": "test-placeholder-secret"}

    def payload(self, **overrides):
        value = {
            "telegram_id": 123456789,
            "username": "vlad",
            "first_name": "Vladyslav",
            "last_name": "Fedchenko",
            "language_code": "ru",
        }
        value.update(overrides)
        return value

    def post(self, payload=None, **headers):
        return self.client.post(
            self.url,
            payload if payload is not None else self.payload(),
            format="json",
            **(headers or self.headers),
        )

    def test_creates_bot_managed_user_and_returns_tokens_and_safe_profile(self):
        response = self.post()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(set(response.data), {"access", "refresh", "user"})
        user = User.objects.get(telegram_id=123456789)
        self.assertEqual(user.email, "telegram-123456789@bot.ludora.invalid")
        self.assertFalse(user.has_usable_password())
        self.assertNotIn("password", response.data["user"])
        self.assertNotIn("telegram_id", response.data["user"])

    def test_duplicate_sync_reuses_one_user(self):
        first = self.post()
        second = self.post(self.payload(first_name="Updated"))

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(User.objects.filter(telegram_id=123456789).count(), 1)
        self.assertEqual(User.objects.get(telegram_id=123456789).first_name, "Updated")

    def test_optional_metadata_can_be_missing_and_is_updated(self):
        self.post(self.payload(username=None, last_name=None, language_code=None))
        user = User.objects.get(telegram_id=123456789)
        self.assertEqual(user.telegram_username, "")
        self.assertEqual(user.last_name, "")
        self.assertEqual(user.telegram_language_code, "")

    def test_database_enforces_unique_telegram_id(self):
        User.objects.create_user(
            email="one@example.com", password=None, telegram_id=123456789
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.create_user(
                email="two@example.com", password=None, telegram_id=123456789
            )

    def test_invalid_telegram_id_is_rejected(self):
        response = self.post(self.payload(telegram_id=0))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_missing_or_invalid_secret_is_rejected_without_creating_user(self):
        for secret in ("", "wrong"):
            response = self.post(HTTP_X_BOT_INTERNAL_SECRET=secret)
            self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertFalse(User.objects.exists())

    @override_settings(BOT_INTERNAL_SECRET="")
    def test_empty_server_secret_fails_closed(self):
        self.assertEqual(self.post().status_code, status.HTTP_401_UNAUTHORIZED)

    def test_returned_access_authenticates_protected_endpoint(self):
        response = self.post()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")
        profile = self.client.get("/api/auth/me/")
        self.assertEqual(profile.status_code, status.HTTP_200_OK)

    def test_openapi_documents_telegram_request_without_password(self):
        response = self.client.get("/api/schema/", HTTP_ACCEPT="application/json")
        operation = response.data["paths"][self.url]["post"]
        reference = operation["requestBody"]["content"]["application/json"]["schema"]["$ref"]
        properties = response.data["components"]["schemas"][
            reference.rsplit("/", maxsplit=1)[-1]
        ]["properties"]
        self.assertIn("telegram_id", properties)
        self.assertNotIn("password", properties)
        self.assertNotIn("access", properties)
