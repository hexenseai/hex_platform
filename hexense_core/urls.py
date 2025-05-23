from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    MessageCreateView, UserProfileView
)

router = DefaultRouter()

urlpatterns = [
    path('', include(router.urls)),
    path('conversations/<uuid:conversation_id>/messages/', MessageCreateView.as_view(), name='message-create'),
    path('userprofile/', UserProfileView.as_view(), name='userprofile'),
    path('userprofile/<uuid:profile_id>/', UserProfileView.as_view(), name='userprofile-detail'),
]