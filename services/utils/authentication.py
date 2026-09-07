from functools import wraps
import jwt
from django.conf import settings
from django.contrib.auth.models import User
from django.http import JsonResponse
from django.utils import timezone

from services.constants import messages


def generate_jwt(user: User) -> str:
    """Issue a JWT carrying the user's id, issued-at, and expiry."""
    now = timezone.now()
    payload = {
        'user_id': user.id,
        'iat': now,
        'exp': now + settings.JWT_EXPIRATION_DELTA,
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def verify_jwt(token: str):
    """Returns the decoded payload, {'expired': True}, or None if invalid."""
    try:
        return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        return {'expired': True}
    except jwt.InvalidTokenError:
        return None


def _extract_bearer_token(auth_header: str):
    """Parses 'Bearer <token>' and returns just the token, or None if malformed."""
    parts = auth_header.split()
    if len(parts) != 2 or parts[0].lower() != 'bearer':
        return None
    return parts[1]


def authenticate(view_func):
    """Decorator: validates the 'Authorization: Bearer <token>' header, attaches request.auth_user."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        if not auth_header:
            return JsonResponse({'success': False, 'message': messages.AUTH_HEADER_MISSING}, status=401)

        token = _extract_bearer_token(auth_header)
        if not token:
            return JsonResponse({'success': False, 'message': messages.AUTH_HEADER_MALFORMED}, status=401)

        decoded = verify_jwt(token)
        if not decoded:
            return JsonResponse({'success': False, 'message': messages.TOKEN_INVALID}, status=401)
        if decoded.get('expired'):
            return JsonResponse({'success': False, 'message': messages.TOKEN_EXPIRED}, status=401)

        user = User.objects.filter(id=decoded.get('user_id'), is_active=True).first()
        if not user:
            return JsonResponse({'success': False, 'message': messages.USER_NOT_FOUND}, status=401)

        request.auth_user = user
        return view_func(request, *args, **kwargs)
    return wrapper


class Authentication:
    """
    Mixin for class-based views that require a valid JWT.
    Usage: class MyView(Authentication, generics.ListAPIView): ...
    """
    @classmethod
    def as_view(cls, **initkwargs):
        view = super().as_view(**initkwargs)
        return authenticate(view)
