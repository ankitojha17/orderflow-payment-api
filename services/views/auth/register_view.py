from django.contrib.auth.models import User
from rest_framework import generics, status

from services.serializer import RegisterSerializer, UserSerializer
from services.utils.response_handler import ResponseHandler
from services.constants import messages


class RegisterView(generics.CreateAPIView):
    """
    Public endpoint. The serializer only validates (e.g. username uniqueness);
    the actual write happens here, in the view.
    """
    serializer_class = RegisterSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = User.objects.create_user(
            username=serializer.validated_data['username'],
            email=serializer.validated_data.get('email', ''),
            password=serializer.validated_data['password'],
        )

        return ResponseHandler(
            message=messages.REGISTER_SUCCESS,
            data=UserSerializer(user).data,
            status=status.HTTP_201_CREATED,
        )
