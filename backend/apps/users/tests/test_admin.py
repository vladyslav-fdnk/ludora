from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.users.admin import CustomUserAdmin

User = get_user_model()


class UserAdminTests(TestCase):
    def test_custom_user_is_registered_with_email_configuration(self):
        model_admin = admin.site._registry[User]

        self.assertIsInstance(model_admin, CustomUserAdmin)
        self.assertIn("email", model_admin.list_display)
        self.assertIn("email", model_admin.search_fields)
        configured_fields = {
            field
            for _, options in (*model_admin.fieldsets, *model_admin.add_fieldsets)
            for field in options["fields"]
        }
        self.assertNotIn("username", configured_fields)
        self.assertIn("telegram_username", configured_fields)

    def test_admin_creation_form_hashes_password(self):
        form = CustomUserAdmin.add_form(
            data={
                "email": "created-in-admin@example.com",
                "password1": "StrongAdminPassword123!",
                "password2": "StrongAdminPassword123!",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        user = form.save()
        self.assertNotEqual(user.password, "StrongAdminPassword123!")
        self.assertTrue(user.check_password("StrongAdminPassword123!"))
