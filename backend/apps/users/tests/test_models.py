from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase

User = get_user_model()


class UserManagerTests(TestCase):
    def test_create_user_with_email(self):
        user = User.objects.create_user(
            email="Person@EXAMPLE.com",
            password="password123",
        )

        self.assertEqual(user.email, "Person@example.com")
        self.assertTrue(user.check_password("password123"))
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

    def test_create_user_requires_email(self):
        with self.assertRaisesMessage(ValueError, "email address must be provided"):
            User.objects.create_user(email="", password="password123")

    def test_create_superuser(self):
        user = User.objects.create_superuser(
            email="admin@example.com",
            password="password123",
        )

        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)

    def test_create_superuser_validates_flags(self):
        with self.assertRaisesMessage(ValueError, "is_staff=True"):
            User.objects.create_superuser(
                email="admin@example.com",
                password="password123",
                is_staff=False,
            )

        with self.assertRaisesMessage(ValueError, "is_superuser=True"):
            User.objects.create_superuser(
                email="admin@example.com",
                password="password123",
                is_superuser=False,
            )

    def test_database_rejects_case_insensitive_duplicate_email(self):
        User.objects.create_user(email="Person@example.com", password="password123")

        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.create_user(
                email="person@example.com",
                password="password123",
            )
