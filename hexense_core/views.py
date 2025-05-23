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
    

class MessageCreateView(CreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = MessageSerializer

    def cosine_similarity(self, vec1, vec2):
        if vec1 is None or vec2 is None:
            return 0.0
        vec1 = np.array(vec1)
        vec2 = np.array(vec2)
        if vec1.shape != vec2.shape:
            return 0.0
        return float(np.dot(vec1, vec2) / (np.linalg.norm(vec1) * np.linalg.norm(vec2)))

    def create(self, request, *args, **kwargs):
        conversation_id = self.kwargs.get("conversation_id")
        gpt_package_id = request.data.get("gpt_package")
        profile_id = request.data.get("profile") 

        _embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
        TOPIC_SIMILARITY_THRESHOLD = 0.75  # Ayarlanabilir

        try:
            # Konuşma ve GPT paketi doğrulaması
            conversation = Conversation.objects.get(id=conversation_id, user_profile_id=profile_id)
            gpt_package = GptPackage.objects.get(id=gpt_package_id) if gpt_package_id else None
            profile = UserProfile.objects.get(id=profile_id)
            # Kullanıcı mesajını kaydet
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            user_message = serializer.validated_data['content']

            # --- TOPIC EMBEDDING KONTROLÜ ---
            new_message_embedding = _embedding_model.encode(user_message).tolist()
            topic_changed = False
            if conversation.topic_embedding:
                similarity = self.cosine_similarity(conversation.topic_embedding, new_message_embedding)
                if similarity < TOPIC_SIMILARITY_THRESHOLD:
                    # Konu değişti, yeni bir conversation başlat
                    topic_changed = True
            else:
                similarity = 1.0  # İlk mesaj veya topic yok

            if topic_changed:
                # Yeni conversation oluştur
                new_conversation = Conversation.objects.create(
                    user_profile=profile,
                    topic=user_message,
                    topic_embedding=new_message_embedding
                )
                conversation = new_conversation

            if topic_changed:
                # Yeni conversation için son mesajı topic olarak kullan
                conversation.topic = user_message
                conversation.topic_embedding = new_message_embedding
                conversation.save()
            else:
                # Konuşmaya bağlı mesajları al ve transformers ile özetle
                from transformers import pipeline
                
                conversation_messages = Message.objects.filter(conversation=conversation).order_by('timestamp')
                if conversation_messages.exists():
                    # Yerel/hızlı model kullan - facebook/bart-large-cnn yerine daha küçük model
                    summarizer = pipeline("summarization", model="facebook/bart-small-cnn", device=-1)  # CPU'da çalıştır
                    
                    # Tüm mesajları birleştir
                    all_messages = " ".join([msg.content for msg in conversation_messages])
                    
                    # Metni özetle (max 130 token)
                    summary = summarizer(all_messages, max_length=130, min_length=30, do_sample=False)[0]['summary_text']
                    
                    # Yeni özet için embedding oluştur
                    new_summary_embedding = _embedding_model.encode(summary).tolist()
                    
                    # Önceki özet ile benzerlik kontrolü
                    if conversation.topic_embedding:
                        similarity = self.cosine_similarity(conversation.topic_embedding, new_summary_embedding)
                        # Benzerlik düşükse güncelle
                        if similarity < TOPIC_SIMILARITY_THRESHOLD:
                            conversation.topic = summary
                            conversation.topic_embedding = new_summary_embedding
                    else:
                        # İlk özet ise direkt kaydet
                        conversation.topic = summary
                        conversation.topic_embedding = new_summary_embedding
                else:
                    # İlk mesaj ise direkt mesajı topic olarak kullan
                    conversation.topic = user_message
                    conversation.topic_embedding = _embedding_model.encode(user_message).tolist()
                
                conversation.save()

            message = serializer.save(
                conversation=conversation,
                sender='user',
                content=user_message,
                gpt_package=gpt_package
            )

            previous_messages = Message.objects.filter(
                conversation=conversation
            ).order_by('timestamp')[:10]

            messages = []
            for msg in previous_messages:
                role = "user" if msg.sender == "user" else "assistant"
                messages.append({
                    "role": role,
                    "content": msg.content
                })
            messages.append({"role": "user", "content": user_message})

            llm_result = call_model(gpt_package, profile, messages)

            gpt_reply = llm_result.get("content", "Üzgünüm, bir yanıt alınamadı.")
            gpt_actions = llm_result.get("actions", None)

            Message.objects.create(
                conversation=conversation,
                sender='gpt',
                content=gpt_reply,
                gpt_package=gpt_package,
                actions=gpt_actions
            )

            conversation.updated_at = now()
            conversation.save()

            return Response({
                "response": gpt_reply,
                "actions": gpt_actions,
                "conversation_id": str(conversation.id),
                "gpt_package_id": str(gpt_package.id) if gpt_package else None
            }, status=status.HTTP_200_OK)

        except Conversation.DoesNotExist:
            return Response({"error": "Konuşma bulunamadı"}, status=status.HTTP_404_NOT_FOUND)
        except GptPackage.DoesNotExist:
            return Response({"error": "GPT paketi bulunamadı"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({
                "response": f"Üzgünüm, bir hata oluştu: {str(e)}"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    


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