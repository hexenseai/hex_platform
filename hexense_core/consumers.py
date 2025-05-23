from channels.generic.websocket import AsyncWebsocketConsumer
import json
import uuid
import datetime
import numpy as np
import openai
from asgiref.sync import sync_to_async
from .models import Conversation, Message, UserProfile, GptPackage
from .semantic import find_best_gpt_package
from .llm_dispatcher import get_gpt_package_services
from .tools import run_tool


class ChatConsumer(AsyncWebsocketConsumer):
    similarity_threshold = 0.85
    async def connect(self):
        self.user_profile = None
        self.gpt_package = None
        self.conversation = None
        self.contexts = []
        self.active_context_index = None
        # Kullanıcı doğrulaması
        user = self.scope.get('user')
        if not user or not user.is_authenticated:
            await self.close()
            return
        await self.accept()
        await self.send(text_data=json.dumps({"type": "connection", "message": "WebSocket bağlantısı kuruldu!"}))
        # Store user info using WhoAmISerializer format
        self.user_info = {
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'profiles': [
                {
                    'id': profile.id,
                    'company': {
                        'id': profile.company.id,
                        'name': profile.company.name
                    } if profile.company else None,
                    'role': {
                        'id': profile.role.id,
                        'name': profile.role.name
                    } if profile.role else None,
                    'is_current': profile.is_current,
                    'gpt_packages': [
                        {
                            'id': pkg.id,
                            'name': pkg.name,
                            'description': pkg.description,
                            'is_default': pkg.is_default,
                            'group': pkg.group.id if pkg.group else None
                        }
                        for pkg in profile.role.gpt_packages.all()
                    ] if profile.role else []
                }
                for profile in user.profiles.all()
            ],
            'current_profile': next(
                (profile for profile in user.profiles.all() if profile.is_current),
                None
            )
        }

    async def disconnect(self, close_code):
        # Bağlantı kopunca state temizlenebilir
        self.user_profile = None
        self.gpt_package = None
        self.conversation = None

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
        except Exception:
            await self.send(text_data=json.dumps({"type": "error", "message": "Geçersiz veri formatı."}))
            return

        event_type = data.get("type")
        if event_type == "profile_change":
            profile_id = data.get("profile_id")
            try:
                self.user_profile = await UserProfile.objects.aget(id=profile_id)
                await self.send(text_data=json.dumps({
                    "type": "profile_change_ack",
                    "profile_id": str(self.user_profile.id),
                }))
            except UserProfile.DoesNotExist:
                await self.send(text_data=json.dumps({
                    "type": "error",
                    "message": "Profil bulunamadı."
                }))
                return
        elif event_type == "gpt_package_change":
            gpt_package_id = data.get("gpt_package_id")
            try:
                self.gpt_package = await GptPackage.objects.aget(id=gpt_package_id)
                await self.send(text_data=json.dumps({
                    "type": "gpt_package_change_ack",
                    "gpt_package_id": str(self.gpt_package.id),
                }))
            except GptPackage.DoesNotExist:
                await self.send(text_data=json.dumps({
                    "type": "error",
                    "message": "GPT paketi bulunamadı."
                }))
                return
        elif event_type == "chat_message":
            message_content = data.get("message")
            await self.change_context(message_content)
            await self.change_gpt_package(message_content)
            #TODO: context ile ilgili veriler db den çekilerek system mesajı için hafıza oluşturulacak.
            system_message = await self.build_system_message()
            # Chat message için response oluştur
            try:
                response = await self.generate_response(system_message, message_content)
            except Exception as e:
                await self.send(text_data=json.dumps({
                    "type": "error", 
                    "message": f"Mesaj işleme hatası: {str(e)}"
                }))
                return
        else:
            await self.send(text_data=json.dumps({"type": "error", "message": "Bilinmeyen event tipi."}))

    async def generate_response(self, system_message: str, message_content: str):
        # Conversation için yeni mesaj oluştur
        user_message = await Message.objects.acreate(
            conversation=self.conversation,
            content=message_content,
            sender='user'
        )

        # GPT paketi için araçları al
        tools = await sync_to_async(get_gpt_package_services)(self.gpt_package)
        tools_description = "\n".join([f"- {tool['name']}: {tool['description']}" for tool in tools]) if tools else ""

        # Mesaj geçmişini al
        messages = [
            {"role": "system", "content": system_message},
            {"role": "system", "content": f"Kullanılabilir araçlar:\n{tools_description}" if tools_description else ""}
        ]

        # Son 10 mesajı ekle
        async for msg in Message.objects.filter(conversation=self.conversation).order_by('-timestamp')[:10]:
            messages.append({
                "role": "assistant" if msg.sender == "assistant" else "user",
                "content": msg.content
            })
        messages.reverse()

        # Kullanıcının son mesajını ekle
        messages.append({"role": "user", "content": message_content})

        # Model yanıtını al
        response = None
        tool_calls_remaining = True
        max_tool_calls = 5
        tool_call_count = 0

        while tool_calls_remaining and tool_call_count < max_tool_calls:
            # OpenAI API çağrısı
            try:
                completion = await openai.ChatCompletion.acreate(
                    model=self.gpt_package.model.name,
                    messages=messages,
                    tools=[{
                        "type": "function",
                        "function": {
                            "name": tool["name"],
                            "description": tool["description"],
                            "parameters": tool["parameters"]
                        }
                    } for tool in tools] if tools else None,
                    tool_choice="auto"
                )
                
                response = completion.choices[0].message.content or ""
                tool_calls = []
                
                if hasattr(completion.choices[0].message, 'tool_calls'):
                    tool_calls = [{
                        "name": tool_call.function.name,
                        "arguments": tool_call.function.arguments
                    } for tool_call in completion.choices[0].message.tool_calls]

            except Exception as e:
                await self.send(text_data=json.dumps({
                    "type": "error",
                    "message": f"OpenAI API hatası: {str(e)}"
                }))
                return

            # Yanıtı chunk'lar halinde gönder
            chunk_size = 100
            for i in range(0, len(response), chunk_size):
                chunk = response[i:i + chunk_size]
                await self.send(text_data=json.dumps({
                    "type": "assistant_message_chunk",
                    "chunk": chunk,
                    "is_final": i + chunk_size >= len(response) and not tool_calls
                }))

            # Tool calls varsa işle
            if tool_calls:
                tool_call_count += 1
                for tool_call in tool_calls:
                    tool_result = await sync_to_async(run_tool)(
                        tool_call["name"],
                        tool_call["arguments"],
                        self.user_profile
                    )
                    messages.append({
                        "role": "tool",
                        "name": tool_call["name"],
                        "content": json.dumps(tool_result)
                    })
            else:
                tool_calls_remaining = False

        # Son mesajı veritabanına kaydet
        await Message.objects.acreate(
            conversation=self.conversation,
            content=response,
            sender='assistant'
        )

        # UI aksiyonlarını gönder
        if hasattr(completion.choices[0].message, 'actions'):
            await self.send(text_data=json.dumps({
                "type": "actions",
                "actions": completion.choices[0].message.actions
            }))

        return response
    

    async def change_context(self, message_content):
        if not self.user_profile or not self.user_profile.company:
            await self.send(text_data=json.dumps({"type": "error", "message": "Kullanıcı profili veya şirket bilgisi eksik."}))
            return
        embedding_response = await sync_to_async(openai.Embedding.create)(
            input=message_content,
            model="text-embedding-ada-002",
            api_key=self.user_profile.company.openai_api_key
        )
        new_vec = np.array(embedding_response['data'][0]['embedding'])

        # 2. En benzer context'i bul
        most_similar_index = None
        highest_sim = -1.0
        for i, ctx in enumerate(self.contexts):
            sim = np.dot(new_vec, ctx['vector'])
            if sim > highest_sim:
                most_similar_index = i
                highest_sim = sim

        # 3. Benzerlik eşik kontrolü
        if highest_sim > self.similarity_threshold:
            # Mevcut context'e devam et
            self.active_context_index = most_similar_index
            ctx = self.contexts[most_similar_index]
            ctx['vector'] = 0.7 * ctx['vector'] + 0.3 * new_vec
            ctx['vector'] = ctx['vector'] / np.linalg.norm(ctx['vector'])  # normalize
            # Optionel: özet güncelleme ileride yapılabilir
        else:
            # Yeni context oluştur
            new_conversation = await Conversation.objects.acreate(user_profile=self.user_profile)
            self.active_context_index = len(self.contexts)
            self.contexts.append({
                "conversation": new_conversation,
                "vector": new_vec / np.linalg.norm(new_vec),
                "summary": f"{message_content[:100]}...",
                "active": True
            })

        # 4. Güncel conversation'ı referansa al
        self.conversation = self.contexts[self.active_context_index]['conversation']

        await self.send(text_data=json.dumps({
            "type": "context_update",
            "active_context_index": self.active_context_index,
            "conversation_id": str(self.conversation.id),
            "context_similarity": float(highest_sim)
        }))

    async def change_gpt_package(self, message_content):
        if not self.user_profile:
            await self.send(text_data=json.dumps({"type": "error", "message": "Kullanıcı profili eksik."}))
            return
        current_package = self.gpt_package

        # Aktif context özeti
        if self.active_context_index is not None:
            ctx = self.contexts[self.active_context_index]
            summary = ctx.get("summary", "")
            context_conversation = ctx["conversation"]
        else:
            summary = ""
            context_conversation = None

        combined_input = f"Geçmiş konuşma özeti: {summary}\nKullanıcının mesajı: {message_content}"

        best_package, score = await sync_to_async(find_best_gpt_package)(combined_input)

        if not best_package or score < 0.75:
            await self.send(text_data=json.dumps({
                "type": "gpt_package_skip",
                "reason": "Uygun GPT paketi bulunamadı veya benzerlik düşük.",
                "score": score
            }))
            return

        # Eğer aynı GPT paketi zaten atanmışsa hiçbir şey yapma
        if current_package and best_package.id == current_package.id:
            return

        # 1. Farklı bir GPT önerildi → şimdi karar vermeliyiz
        # Bu context'e bağlı conversation üzerinde hiç mesaj var mı?
        has_messages = await Message.objects.filter(conversation=context_conversation).aexists()

        if context_conversation.gpt_package_id != best_package.id:
            if has_messages:
                # Yeni context ve conversation başlat
                new_conversation = await Conversation.objects.acreate(
                    user_profile=self.user_profile,
                    gpt_package=best_package
                )
                new_context = {
                    "conversation": new_conversation,
                    "vector": ctx["vector"],  # Mevcut vectorü devralabilir veya yeni başlatılabilir
                    "summary": summary,
                    "active": True
                }
                self.contexts.append(new_context)
                self.active_context_index = len(self.contexts) - 1
                self.conversation = new_conversation
            else:
                # Mevcut conversation'ı güncelle (henüz hiç mesaj yok)
                context_conversation.gpt_package = best_package
                await sync_to_async(context_conversation.save)()
                self.conversation = context_conversation

            # Aktif GPT paketi güncellenir
            self.gpt_package = best_package

            await self.send(text_data=json.dumps({
                "type": "gpt_package_update",
                "gpt_package_id": str(best_package.id),
                "gpt_package_name": best_package.name,
                "score": score,
                "new_conversation": has_messages  # Yeni context açıldı mı?
            }))

    async def build_system_message(self):
        # Safely get user information with fallbacks
        username = self.user_profile.user.get_full_name() or self.user_profile.user.username
        gpt_preferences = getattr(self.user_profile, 'gpt_preferences', '') if self.user_profile else ""
        work_experience = getattr(self.user_profile, 'work_experience_notes', '') if self.user_profile else ""

        # Safely get role information
        role = getattr(self.user_profile.role, 'name', 'Tanımsız') if self.user_profile and self.user_profile.role else "Tanımsız"
        role_desc = getattr(self.user_profile.role, 'description', '') if self.user_profile and self.user_profile.role else ""

        # Safely get department information
        department = getattr(self.user_profile.department, 'name', 'Tanımsız') if self.user_profile and self.user_profile.department else "Tanımsız"
        department_desc = getattr(self.user_profile.department, 'description', '') if self.user_profile and self.user_profile.department else ""

        # Safely get company information
        company = getattr(self.user_profile.company, 'name', 'Tanımsız') if self.user_profile and self.user_profile.company else "Tanımsız"
        company_desc = getattr(self.user_profile.company, 'description', '') if self.user_profile and self.user_profile.company else ""

        gpt_info = self.gpt_package.description or ""

        # Get today's date and time
        now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        # Get last user action/message timestamp
        last_action = Message.objects.filter(conversation__user_profile=self.user_profile, sender='user').order_by('-timestamp').first()
        last_action_str = last_action.timestamp.strftime('%Y-%m-%d %H:%M:%S') if last_action else 'Yok'


        # Conditional info blocks
        company_block = f"- Departmanı: {department} → {department_desc}\n- Şirketi: {company} → {company_desc}" if getattr(gpt_package, 'include_company_info', False) else ""
        personal_block = f"- İş Deneyimi ve Uzmanlık Alanları:\n\"\"\"{work_experience}\"\"\"" if getattr(gpt_package, 'include_personal_info', False) else ""

        base_prompt = f"""
Sen Hexense platformunda '{gpt_package.name}' isimli özel amaçlı bir yapay zeka yardımcısısın.

📅 Bugünün tarihi ve saati: {now_str}
🕑 Kullanıcının son işlemi: {last_action_str}

📌 Kullanıcı profili:
- Kullanıcı adı: {username}
- Rolü: {role} → {role_desc}
{company_block}
- GPT Tercihleri:
\"\"\"{gpt_preferences}\"\"\"
{personal_block}

📦 GPT paket açıklaması:
\"\"\"{gpt_info}\"\"\"

⛔ Lütfen sistemin güvenlik kurallarına uy. Kullanıcının şirket dışı kaynaklara doğrudan erişimi yoktur.
✅ Fonksiyonlar (tool calling) varsa onları kullanarak işlem yap.
⛳ Her yanıtın sonunda gerekiyorsa bir `actions` listesi üret. UI bileşenlerini tetikleyebiliriz.

🎯 Hedefin:
Kullanıcının işini kolaylaştırmak, ona öneriler sunmak ve gerektiğinde onun adına işlemler başlatmak.
""".strip()
        # Ek system_prompt varsa paketten dahil et
        if self.gpt_package.system_prompt:
            base_prompt += f"\n\n📘 Sistem Ek Açıklaması:\n{self.gpt_package.system_prompt}"

        return base_prompt