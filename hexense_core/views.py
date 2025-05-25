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
from django.contrib.auth.models import User
from django.db import transaction


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


class RegisterView(APIView):
    permission_classes = [permissions.AllowAny]

    @transaction.atomic
    def post(self, request):
        first_name = request.data.get('first_name')
        last_name = request.data.get('last_name')
        email = request.data.get('email')
        password = request.data.get('password')
        if not all([first_name, last_name, email, password]):
            return Response({'error': 'Tüm alanlar zorunludur.'}, status=status.HTTP_400_BAD_REQUEST)
        if User.objects.filter(username=email).exists():
            return Response({'error': 'Bu e-posta ile zaten bir kullanıcı var.'}, status=status.HTTP_400_BAD_REQUEST)
        user = User.objects.create_user(username=email, email=email, password=password, first_name=first_name, last_name=last_name)
        # Hexense AI şirketini bul veya oluştur
        company, _ = Company.objects.get_or_create(name='Hexense AI', defaults={'description': 'Default company for all users'})
        # İş departmanını bul veya oluştur
        department, _ = Department.objects.get_or_create(name='Müşteri', company=company, defaults={'description': 'Varsayılan iş departmanı'})
        # Misafir rolünü bul veya oluştur
        role, _ = Role.objects.get_or_create(name='Misafir', company=company, department=department, defaults={'description': 'Varsayılan misafir rolü'})

        # Profil oluştur
        profile = UserProfile.objects.create(user=user, company=company, department=department, role=role, is_current=True)
        return Response({'message': 'Kayıt başarılı.'}, status=status.HTTP_201_CREATED)