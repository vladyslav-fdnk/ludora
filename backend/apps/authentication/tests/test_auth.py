from rest_framework.test import APITestCase
from rest_framework import status

from django.contrib.auth import get_user_model


User = get_user_model()


class RegisterTests(APITestCase):

    def test_user_can_register(self):

        response = self.client.post(
            "/api/auth/register/",
            {
                "username": "vlad",
                "email": "vlad@test.com",
                "password": "password123",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

        self.assertTrue(
            User.objects.filter(
                username="vlad"
            ).exists()
        )


class LoginTests(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username="vlad",
            email="vlad@test.com",
            password="password123",
        )


    def test_user_can_login(self):

        response = self.client.post(
            "/api/auth/login/",
            {
                "username": "vlad",
                "password": "password123",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assertIn(
            "access",
            response.data,
        )

        self.assertIn(
            "refresh",
            response.data,
        )
        

class MeTests(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username="vlad",
            email="vlad@test.com",
            password="password123",
        )


    def test_authenticated_user_can_get_profile(self):

        self.client.force_authenticate(
            user=self.user
        )

        response = self.client.get(
            "/api/auth/me/"
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assertEqual(
            response.data["username"],
            "vlad",
        )


    def test_anonymous_user_cannot_get_profile(self):

        response = self.client.get(
            "/api/auth/me/"
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )