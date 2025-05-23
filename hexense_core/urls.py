from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import UserProfileView

router = DefaultRouter()

urlpatterns = [
    path('', include(router.urls)),
    path('userprofile/', UserProfileView.as_view(), name='userprofile'),
    path('userprofile/<uuid:profile_id>/', UserProfileView.as_view(), name='userprofile-detail'),
]