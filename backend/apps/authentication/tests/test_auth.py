from django.contrib.auth import get_user_model
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
            {"id": self.user.id, "email": "vlad@test.com"},
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
