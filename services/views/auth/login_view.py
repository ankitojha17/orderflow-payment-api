from django.contrib.auth import authenticate
from rest_framework import generics, status

from services.serializer import LoginSerializer
from services.utils.authentication import generate_jwt
from services.utils.response_handler import ResponseHandler
from services.constants import messages


class LoginView(generics.CreateAPIView):
    """
    Public endpoint. Serializer only checks that username/password were
    supplied; the credential check itself is business logic, done here.
    """
    serializer_class = LoginSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = authenticate(
            username=serializer.validated_data['username'],
            password=serializer.validated_data['password'],
        )

        # Negative case first.
        if not user:
            return ResponseHandler(
                success=False, message=messages.INVALID_CREDENTIALS, status=status.HTTP_401_UNAUTHORIZED
            )

        token = generate_jwt(user)
        return ResponseHandler(
            message=messages.LOGIN_SUCCESS,
            data={'token': token, 'user_id': user.id, 'username': user.username},
            status=status.HTTP_200_OK,
        )
