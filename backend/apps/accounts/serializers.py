from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from .models import User


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(write_only=True, trim_whitespace=False, style={"input_type": "password"})


class MeSerializer(serializers.ModelSerializer):
    role_label = serializers.CharField(source="get_role_display", read_only=True)

    class Meta:
        model = User
        fields = ["id", "username", "first_name", "last_name", "email", "role", "role_label", "last_login"]
        read_only_fields = fields


class UserAdminSerializer(serializers.ModelSerializer):
    """Used by administrators to create and manage users. Passwords are write-only and hashed."""

    password = serializers.CharField(write_only=True, required=False, style={"input_type": "password"})
    role_label = serializers.CharField(source="get_role_display", read_only=True)

    class Meta:
        model = User
        fields = [
            "id", "username", "first_name", "last_name", "email", "role", "role_label",
            "is_active", "last_login", "date_joined", "password",
        ]
        read_only_fields = ["id", "last_login", "date_joined", "role_label"]

    def validate(self, attrs):
        request = self.context.get("request")
        if self.instance is not None and request is not None and self.instance.pk == request.user.pk:
            # Stops the last administrator from locking everyone out by accident.
            if "role" in attrs and attrs["role"] != self.instance.role:
                raise serializers.ValidationError({"role": "You can't change your own role."})
            if attrs.get("is_active") is False:
                raise serializers.ValidationError({"is_active": "You can't deactivate your own account."})
        password = attrs.get("password")
        if self.instance is None and not password:
            raise serializers.ValidationError({"password": "A password is required for new users."})
        if password:
            candidate = self.instance or User(**{k: v for k, v in attrs.items() if k != "password"})
            validate_password(password, user=candidate)
        return attrs

    def create(self, validated_data):
        password = validated_data.pop("password")
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance
