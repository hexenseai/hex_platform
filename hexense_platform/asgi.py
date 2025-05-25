"""
ASGI config for hexense_platform project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.1/howto/deployment/asgi/
"""

import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack

from django.urls import path
from hexense_core.consumers import ChatConsumer # Kendi consumer'ınızın yolu

# JWT tabanlı WebSocket kimlik doğrulaması için custom middleware
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from urllib.parse import parse_qs

@database_sync_to_async
def get_user(scope):
    # Önce header'dan dene
    headers = dict(scope['headers'])
    token_key = None
    if b'authorization' in headers:
        try:
            token_name, token_key = headers[b'authorization'].decode().split()
            if token_name != 'Bearer':
                token_key = None
        except Exception:
            token_key = None
    # Header yoksa, query_string'den dene
    if not token_key:
        query_string = scope.get('query_string', b'').decode()
        query_params = parse_qs(query_string)
        token_list = query_params.get('token')
        if token_list:
            token_key = token_list[0]
    if token_key:
        try:
            validated_token = JWTAuthentication().get_validated_token(token_key)
            user = JWTAuthentication().get_user(validated_token)
            return user
        except (InvalidToken, TokenError, ValueError):
            pass
    return AnonymousUser()

class TokenAuthMiddleware:
    """
    Custom middleware that takes a token from the query string and authenticates it.
    """
    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        # WebSocket bağlantısı için query_string'den token'ı al
        # Veya HTTP başlıklarından Authorization başlığını kullan
        # Bu örnekte Authorization başlığını kullanıyoruz
        scope['user'] = await get_user(scope)
        return await self.inner(scope, receive, send)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hexense_platform.settings')
application = get_asgi_application()

# WebSocket routing
application = ProtocolTypeRouter({
    "http": application,
    "websocket": TokenAuthMiddleware( # AuthMiddlewareStack yerine custom middleware
        URLRouter([
            path("ws/chat/", ChatConsumer.as_asgi()),
        ])
    ),
})