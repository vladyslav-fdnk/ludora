from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from rest_framework import serializers
from rest_framework.validators import UniqueValidator
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

User = get_user_model()


class RegisterSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(
        validators=[
            UniqueValidator(
                queryset=User.objects.all(),
                lookup="iexact",
            )
        ]
    )
    password = serializers.CharField(
        write_only=True,
    )

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "password",
        ]
        read_only_fields = ["id"]

    def create(self, validated_data):
        user = User.objects.create_user(**validated_data)

        return user


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "telegram_username",
            "telegram_language_code",
            "date_joined",
        ]
        read_only_fields = fields


class EmailTokenObtainPairSerializer(TokenObtainPairSerializer):
    pass


class TelegramAuthenticationSerializer(serializers.Serializer):
    telegram_id = serializers.IntegerField(min_value=1, max_value=9223372036854775807)
    username = serializers.CharField(
        required=False, allow_blank=True, allow_null=True, max_length=32
    )
    first_name = serializers.CharField(
        required=False, allow_blank=True, allow_null=True, max_length=150
    )
    last_name = serializers.CharField(
        required=False, allow_blank=True, allow_null=True, max_length=150
    )
    language_code = serializers.CharField(
        required=False, allow_blank=True, allow_null=True, max_length=35
    )

    def create(self, validated_data):
        telegram_id = validated_data["telegram_id"]
        # The unique telegram_id constraint is the final concurrency guard. If
        # another request wins the insert race, retry as a lookup.
        try:
            with transaction.atomic():
                user = User.objects.filter(telegram_id=telegram_id).first()
                if user is None:
                    user = User.objects.create_user(
                        email=f"telegram-{telegram_id}@bot.ludora.invalid",
                        password=None,
                        telegram_id=telegram_id,
                        **self._metadata(validated_data),
                    )
        except IntegrityError:
            user = User.objects.get(telegram_id=telegram_id)

        changed = []
        for field, value in self._metadata(validated_data).items():
            if getattr(user, field) != value:
                setattr(user, field, value)
                changed.append(field)
        if changed:
            user.save(update_fields=changed)
        return user

    @staticmethod
    def _metadata(data):
        return {
            "telegram_username": data.get("username") or "",
            "first_name": data.get("first_name") or "",
            "last_name": data.get("last_name") or "",
            "telegram_language_code": data.get("language_code") or "",
        }


class TelegramAuthenticationResponseSerializer(serializers.Serializer):
    access = serializers.CharField(read_only=True)
    refresh = serializers.CharField(read_only=True)
    user = UserSerializer(read_only=True)
