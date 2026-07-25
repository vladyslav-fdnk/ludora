from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.permissions import IsOwnerOrStaff, IsStaffUser

User = get_user_model()


class PermissionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="owner@example.com")
        self.other_user = User.objects.create_user(email="other@example.com")
        self.staff_user = User.objects.create_user(
            email="staff@example.com",
            is_staff=True,
        )
        self.superuser = User.objects.create_user(
            email="superuser@example.com",
            is_superuser=True,
        )

    def request_for(self, user):
        return SimpleNamespace(user=user)

    def test_staff_permission_uses_django_staff_flag(self):
        permission = IsStaffUser()

        self.assertTrue(permission.has_permission(self.request_for(self.staff_user), None))
        self.assertTrue(permission.has_permission(self.request_for(self.superuser), None))
        self.assertFalse(permission.has_permission(self.request_for(self.user), None))

    def test_owner_or_staff_object_permission(self):
        permission = IsOwnerOrStaff()
        owned_object = SimpleNamespace(user=self.user)

        self.assertTrue(
            permission.has_object_permission(
                self.request_for(self.user),
                None,
                owned_object,
            )
        )
        self.assertFalse(
            permission.has_object_permission(
                self.request_for(self.other_user),
                None,
                owned_object,
            )
        )
        self.assertTrue(
            permission.has_object_permission(
                self.request_for(self.staff_user),
                None,
                owned_object,
            )
        )
        self.assertTrue(
            permission.has_object_permission(
                self.request_for(self.superuser),
                None,
                owned_object,
            )
        )
