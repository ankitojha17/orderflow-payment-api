from django.contrib.auth.models import User
from rest_framework import serializers

from services.constants import messages


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'password']

    def validate_username(self, username):
        if User.objects.filter(username=username).exists():
            raise serializers.ValidationError(messages.USERNAME_ALREADY_EXISTS)
        return username


class LoginSerializer(serializers.Serializer):
    """
    Pure shape + presence validation only. The actual credential check
    (right/wrong password) is a business decision, not a data-shape
    validation — that happens in LoginView.
    """
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email']
