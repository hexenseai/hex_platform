from django.contrib.auth import authenticate, login, logout
from rest_framework import viewsets
from .models import Company, Department, Role, UserProfile, Message, Conversation, GptPackage
from .serializers import CompanySerializer, DepartmentSerializer, RoleSerializer, UserProfileSerializer, MessageSerializer, ConversationSerializer, GptPackageSerializer, WhoAmISerializer
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.utils.timezone import now
from rest_framework.generics import ListCreateAPIView, RetrieveAPIView, CreateAPIView
from rest_framework.permissions import IsAuthenticated
from hexense_core.llm_dispatcher import call_model
from sentence_transformers import SentenceTransformer
import numpy as np


class LoginView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        username = request.data.get('username')
        password = request.data.get('password')
        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            return Response({'message': 'Login successful'}, status=status.HTTP_200_OK)
        else:
            return Response({'error': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)


class LogoutView(APIView):
    def post(self, request):
        logout(request)
        return Response({'message': 'Logged out'}, status=status.HTTP_200_OK)


class WhoAmIView(APIView):
    def get(self, request):
        if not request.user.is_authenticated:
            return Response({'error': 'Not authenticated'}, status=401)
        serializer = WhoAmISerializer(request.user)
        return Response(serializer.data)
    


class UserProfileView(APIView):
    permission_classes = [IsAuthenticated]
    template_name = 'userprofile.html'

    def get(self, request):
        """Kullanıcının tüm profillerini getir"""
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            # AJAX isteği için JSON yanıtı
            profiles = UserProfile.objects.filter(user=request.user)
            serializer = UserProfileSerializer(profiles, many=True)
            return Response(serializer.data)
        else:
            # Sayfa render etme
            return render(request, self.template_name)

    def patch(self, request, profile_id):
        """Belirtilen profili güncelle"""
        try:
            profile = UserProfile.objects.get(id=profile_id, user=request.user)
            
            # Sadece izin verilen alanların güncellenmesi
            allowed_fields = [
                'phone_number', 
                'gpt_preferences', 
                'work_experience_notes'
            ]
            update_data = {
                key: value for key, value in request.data.items() 
                if key in allowed_fields
            }
            
            serializer = UserProfileSerializer(profile, data=update_data, partial=True)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            
        except UserProfile.DoesNotExist:
            return Response(
                {"error": "Profil bulunamadı"}, 
                status=status.HTTP_404_NOT_FOUND
            )