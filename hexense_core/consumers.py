# hexense_core/consumers.py

from channels.generic.websocket import AsyncWebsocketConsumer
import json
import datetime
import uuid
import logging # Logging ekleyelim
from typing import List, Dict, Any, Optional
from asgiref.sync import sync_to_async
from hexense_core.models import Conversation, Message, UserProfile, GptPackage
from hexense_core.semantic import find_best_gpt_package # Bu hala kullanılacak
from hexense_core.utils import run_tool # Araçları çalıştırmak için
from hexense_core import llm_dispatcher # Yeni dispatcher'ımızı import edelim
from hexense_core import semantic


logger = logging.getLogger(__name__)

class ChatConsumer(AsyncWebsocketConsumer):
    similarity_threshold = 0.85 # Bu değer config'den alınabilir
    memory_context_limit = 3  # Qdrant'tan çekilecek geçmiş context sayısı
    context_summary_trigger = 8  # Kaç mesajda bir özet alınacak

    async def connect(self):
        self.user = self.scope.get('user')
        if not self.user or not self.user.is_authenticated:
            await self.close()
            return

        # Aktif kullanıcı profili ve gpt paketi başlangıçta None
        self.user_profile: Optional[UserProfile] = None
        self.gpt_package: Optional[GptPackage] = None
        self.conversation: Optional[Conversation] = None # Aktif konuşma (veya bağlam)
        
        # `contexts` ve `active_context_index` mantığı, konuşma bağımsız hafızaya
        # geçişte yeniden değerlendirilebilir. Şimdilik, her yeni "ana konu" veya
        # GPT paketi değişimi yeni bir `Conversation` objesiyle yönetilebilir.
        # `change_context` ve `change_gpt_package` metodları bu `self.conversation`'ı güncelleyecek.
        # self.contexts = [] 
        # self.active_context_index = None

        await self.accept()
        await self.send(text_data=json.dumps({
            "type": "connection_established", 
            "message": "WebSocket bağlantısı başarıyla kuruldu!"
        }))
        
        # Kullanıcı profillerini ve ilk GPT paketini yükleme mantığı `receive` içinde
        # "profile_change" ve "gpt_package_change" ile yönetilecek.
        # Frontend ilk bağlandığında varsayılan profili ve paketi gönderebilir.

        self.conversations_pool = {}  # {conversation_id: {"summary": ..., "embedding": ..., "timestamp": ...}}

    async def disconnect(self, close_code):
        logger.info(f"WebSocket disconnected for user {self.user.username} with code {close_code}")
        # Gerekirse kaynakları serbest bırakma işlemleri burada yapılabilir.
        pass

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            event_type = data.get("type")
            logger.debug(f"Received event: {event_type} from {self.user.username}, data: {data}")

            if event_type == "profile_change":
                profile_id = data.get("profile_id")
                if not profile_id:
                    await self.send_error("Profil ID'si eksik.")
                    return
                try:
                    # UserProfile'ı user ile birlikte sorgula güvenlik için
                    self.user_profile = await UserProfile.objects.select_related('user', 'company', 'role', 'department').aget(id=profile_id, user=self.user)
                    logger.info(f"User {self.user.username} changed profile to {self.user_profile.id} ({self.user_profile.role.name if self.user_profile.role else 'No Role'})")
                    # Yeni profil seçildiğinde, mevcut konuşmayı ve gpt paketini sıfırlayabiliriz
                    # veya frontend'in yeni bir gpt_package_change göndermesini bekleyebiliriz.
                    self.conversation = None 
                    self.gpt_package = None 
                    await self.send(text_data=json.dumps({
                        "type": "profile_change_ack",
                        "profile_id": str(self.user_profile.id),
                    }))
                except UserProfile.DoesNotExist:
                    logger.warning(f"UserProfile not found or not owned by user. Profile ID: {profile_id}, User: {self.user.username}")
                    await self.send_error("Profil bulunamadı veya size ait değil.")
                    self.user_profile = None # Hatalı durumda sıfırla
                    return

            elif event_type == "gpt_package_change":
                if not self.user_profile:
                    await self.send_error("Önce bir kullanıcı profili seçmelisiniz.")
                    return
                gpt_package_id = data.get("gpt_package_id")
                if not gpt_package_id:
                    await self.send_error("GPT Paket ID'si eksik.")
                    return
                try:
                    # GPT paketinin seçilen role için uygun olup olmadığını kontrol edebiliriz.
                    # Şimdilik doğrudan ID ile alıyoruz.
                    self.gpt_package = await GptPackage.objects.prefetch_related('services').select_related('model').aget(id=gpt_package_id)
                    # GptPackage'ın gerçekten kullanıcının rolüyle ilişkili olup olmadığını kontrol et
                    # if self.user_profile.role not in self.gpt_package.allowed_roles.all(): ...
                    logger.info(f"User {self.user.username} (Profile: {self.user_profile.id}) changed GptPackage to {self.gpt_package.name}")
                    # Yeni GPT paketi seçildiğinde yeni bir konuşma başlatabiliriz.
                    self.conversation = await self.get_or_create_conversation_for_gpt_package()
                    await self.send(text_data=json.dumps({
                        "type": "gpt_package_change_ack",
                        "gpt_package_id": str(self.gpt_package.id),
                        "conversation_id": str(self.conversation.id) if self.conversation else None
                    }))
                except GptPackage.DoesNotExist:
                    logger.warning(f"GptPackage not found. ID: {gpt_package_id}")
                    await self.send_error("GPT Paketi bulunamadı.")
                    self.gpt_package = None # Hatalı durumda sıfırla
                    return
            
            elif event_type == "new_conversation": # Frontend'den yeni sohbet talebi
                if not self.user_profile or not self.gpt_package:
                    await self.send_error("Yeni sohbet başlatmak için profil ve GPT paketi seçili olmalıdır.")
                    return
                self.conversation = await self.get_or_create_conversation_for_gpt_package(force_new=True)
                logger.info(f"User {self.user.username} started new conversation {self.conversation.id} with GptPackage {self.gpt_package.name}")
                await self.send(text_data=json.dumps({
                    "type": "new_conversation_ack",
                    "conversation_id": str(self.conversation.id)
                }))

            elif event_type == "chat_message":
                message_content = data.get("message", "").strip()
                if not message_content:
                    await self.send_error("Mesaj içeriği boş olamaz.")
                    return
                
                if not self.user_profile or not self.gpt_package:
                    await self.send_error("Mesaj göndermeden önce profil ve GPT paketi seçmelisiniz.")
                    return

                if not self.conversation:
                    self.conversation = await self.get_or_create_conversation_for_gpt_package()

                can_continue = await self.evaluate_gpt_package(message_content)
                if not can_continue:
                    return

                await Message.objects.acreate(
                    conversation=self.conversation,
                    sender='user',
                    content=message_content,
                    gpt_package=self.gpt_package
                )

                # --- KONUŞMA KONTEXTİ ÖZETLEME ve QDRANT'A KAYIT ---
                await self.maybe_update_conversation_summary()

                # --- HAFIZA ARAMASI: QDRANT'TAN GEÇMİŞ KONUMLARI ÇEK ---
                memory_contexts = await self.search_memory_contexts(message_content)

                # --- LLM'E GÖNDERİLECEK MESAJ GEÇMİŞİNİ HAZIRLA ---
                history_messages = await self.prepare_message_history()
                history_messages.append({"role": "user", "content": message_content})

                # --- SYSTEM PROMPT OLUŞTURMA ---
                system_prompt = await llm_dispatcher.build_system_prompt(
                    self.user_profile, self.gpt_package
                )
                # Hafıza mesajlarını system prompt'a ekle
                if memory_contexts:
                    memory_block = "\n\n[Geçmiş Konuşma Hafızası]:\n" + "\n".join([
                        f"[{ctx['timestamp']}] {ctx['summary']}" for ctx in memory_contexts
                    ])
                    system_prompt += memory_block

                # --- LLM YANITI ÜRETME (system prompt ile) ---
                await self.generate_response_from_dispatcher_with_system_prompt(history_messages, system_prompt)

            else:
                logger.warning(f"Unknown event type received: {event_type}")
                await self.send_error(f"Bilinmeyen olay tipi: {event_type}")

        except json.JSONDecodeError:
            logger.error("Invalid JSON received from WebSocket.")
            await self.send_error("Geçersiz JSON formatı.")
        except Exception as e:
            logger.error(f"Error processing WebSocket message: {e}", exc_info=True)
            await self.send_error(f"Sunucu hatası: {str(e)}")

    async def send_error(self, message: str):
        await self.send(text_data=json.dumps({"type": "error", "message": message}))

    async def get_or_create_conversation_for_gpt_package(self, force_new: bool = False) -> Conversation:
        """
        Mevcut UserProfile ve GptPackage için aktif bir Conversation bulur veya oluşturur.
        force_new=True ise her zaman yeni bir Conversation oluşturur.
        """
        if not self.user_profile or not self.gpt_package:
            raise ValueError("UserProfile and GptPackage must be set to get/create a conversation.")

        if force_new:
            conv = await Conversation.objects.acreate(
                user_profile=self.user_profile
                # topic ve topic_embedding başlangıçta boş olabilir veya ilk mesajdan sonra güncellenebilir.
            )
            logger.info(f"Forced new conversation {conv.id} for UserProfile {self.user_profile.id} and GptPackage {self.gpt_package.name}")
            return conv

        # Son güncellenen, bu profile ve pakete ait konuşmayı bulmaya çalış
        # Bu mantık, kullanıcının aynı paketle devam ettiği sürece aynı konuşmada kalmasını sağlar.
        # Daha karmaşık "context switching" için bu kısım geliştirilebilir.
        conv = await Conversation.objects.filter(
            user_profile=self.user_profile
        ).order_by('-updated_at').afirst()

        if not conv:
            conv = await Conversation.objects.acreate(
                user_profile=self.user_profile
            )
            logger.info(f"Created new conversation {conv.id} for UserProfile {self.user_profile.id} and GptPackage {self.gpt_package.name}")
        else:
            logger.info(f"Reusing conversation {conv.id} for UserProfile {self.user_profile.id} and GptPackage {self.gpt_package.name}")
        
        return conv

    async def prepare_message_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Veritabanından mevcut konuşma için mesaj geçmişini hazırlar.
        LLM'e gönderilecek formattadır (örn: {"role": "user", "content": "..."}).
        Sistem prompt'u BU FONKSİYONDA EKLENMEZ, llm_dispatcher halleder.
        """
        if not self.conversation:
            return []

        history = []
        # `select_related` ile `gpt_package` ve `tool_calls` (eğer varsa) prefetch edilebilir.
        # Şimdilik basit tutalım.
        db_messages = Message.objects.filter(conversation=self.conversation).order_by('-timestamp')[:limit]
        
        async for msg in db_messages:
            role = "user" if msg.sender == "user" else "assistant"
            # Eğer mesajda LLM'in yaptığı tool_calls varsa, bunları da geçmişe ekleyebiliriz.
            # OpenAI formatı: {"role": "assistant", "content": null, "tool_calls": [...]}
            #                 {"role": "tool", "tool_call_id": ..., "name": ..., "content": ...}
            # Şimdilik sadece content'i alıyoruz. Araç çağırma döngüsü bu kısmı daha karmaşık hale getirecek.
            
            message_entry = {"role": role, "content": msg.content}
            
            # Eğer bu bir asistan mesajıysa ve araç çağrıları içeriyorsa (Message modelinde böyle bir alan varsa)
            # if role == "assistant" and msg.tool_calls_data: # Varsayımsal alan
            #    message_entry["tool_calls"] = msg.tool_calls_data 
            #    if not msg.content: # Eğer sadece tool_call varsa ve içerik yoksa
            #        message_entry["content"] = None 
            
            # Eğer bu bir araç yanıtı mesajıysa (Message modelinde sender='tool' gibi bir ayrım varsa)
            # if msg.sender == "tool" and msg.tool_call_id_data and msg.tool_name_data: # Varsayımsal alanlar
            #    message_entry = {
            #        "role": "tool", 
            #        "tool_call_id": msg.tool_call_id_data,
            #        "name": msg.tool_name_data,
            #        "content": msg.content # Araç sonucu (JSON string)
            #    }
            history.append(message_entry)
        
        history.reverse() # Kronolojik sıraya getir (en eski önce)
        return history

    async def generate_response_from_dispatcher(self, history_messages: List[Dict[str, Any]]):
        """
        `llm_dispatcher.call_model` kullanarak yanıt alır ve stream eder.
        Araç çağırma döngüsünü yönetir.
        """
        if not self.user_profile or not self.gpt_package or not self.conversation:
            logger.error("Cannot generate response: user_profile, gpt_package, or conversation is not set.")
            await self.send_error("Yanıt üretilemedi: Gerekli oturum bilgileri eksik.")
            return

        current_message_history = list(history_messages) # Değişiklikler için kopya al
        full_assistant_response_content = ""
        final_actions_for_ui = []
        
        MAX_TOOL_CYCLES = 5
        tool_cycle_count = 0

        try:
            while tool_cycle_count < MAX_TOOL_CYCLES:
                logger.debug(f"Tool cycle {tool_cycle_count + 1}. History length: {len(current_message_history)}")
                
                # Bayrak: Bu LLM çağrısı turunda herhangi bir metin içeriği stream edildi mi?
                streamed_content_in_this_llm_call = False
                # Bu LLM çağrısı için biriktirilen araçlar (LLM'in çalıştırılmasını istediği)
                llm_requested_tool_calls = []

                async for response_part in llm_dispatcher.call_model(
                    self.gpt_package, 
                    self.user_profile, 
                    current_message_history # Her döngüde güncellenmiş geçmişi gönder
                ):
                    event_type = response_part.get("type")
                    event_data = response_part.get("data")

                    if event_type == "content_chunk":
                        full_assistant_response_content += event_data
                        streamed_content_in_this_llm_call = True
                        await self.send(text_data=json.dumps({
                            "type": "assistant_message_chunk",
                            "chunk": event_data
                        }))
                    elif event_type == "tool_calls_ready":
                        # llm_dispatcher'dan gelen, çalıştırılmaya hazır araç çağrıları
                        llm_requested_tool_calls = event_data 
                        logger.info(f"LLM requested {len(llm_requested_tool_calls)} tools to be called.")
                    elif event_type == "stream_end":
                        logger.debug(f"LLM stream ended. Finish reason: {event_data.get('finish_reason')}")
                        # UI aksiyonları burada `parse_actions` ile ayıklanabilir,
                        # eğer `full_assistant_response_content` içinde [ACTION] direktifleri varsa.
                        # Ancak aksiyonların ayrı bir `event_type` ile gelmesi daha temiz olur.
                        # Şimdilik, stream sonunda `full_assistant_response_content`'i işleyelim.
                        current_ui_actions = llm_dispatcher.parse_actions(full_assistant_response_content)
                        if current_ui_actions:
                            final_actions_for_ui.extend(current_ui_actions)
                            # UI'a gönderilecek metinden [ACTION] kısımlarını temizle
                            full_assistant_response_content = llm_dispatcher.process_model_response_text_for_ui(full_assistant_response_content)
                        break # Bu LLM çağrısının stream'i bitti.
                    elif event_type == "error":
                        logger.error(f"Error from llm_dispatcher: {event_data}")
                        await self.send_error(f"Model hatası: {event_data}")
                        return # Hata durumunda işlemi sonlandır
                
                # LLM Stream'i bitti. Şimdi araçları kontrol et.
                if not llm_requested_tool_calls:
                    # Çalıştırılacak araç yok, döngüden çıkabiliriz.
                    logger.debug("No tool calls requested by LLM in this cycle. Ending tool loop.")
                    break 
                
                # Araçları çalıştırmadan önce, LLM'in bu turda ürettiği (varsa)
                # metin içeriğini ve araç çağırma isteğini geçmişe ekleyelim.
                # OpenAI formatına göre: assistant rolü, content (varsa), tool_calls listesi.
                assistant_message_for_history = {
                    "role": "assistant",
                    "content": full_assistant_response_content if streamed_content_in_this_llm_call else None,
                    "tool_calls": llm_requested_tool_calls # llm_dispatcher'dan gelen formatta
                }
                current_message_history.append(assistant_message_for_history)
                full_assistant_response_content = "" # Bir sonraki LLM yanıtı için sıfırla

                # Araçları çalıştır
                tool_execution_results = []
                for tool_call_request in llm_requested_tool_calls:
                    tool_name = tool_call_request.get("function", {}).get("name")
                    tool_args_str = tool_call_request.get("function", {}).get("arguments")
                    tool_call_id = tool_call_request.get("id")

                    if not tool_name or not tool_args_str or not tool_call_id:
                        logger.error(f"Invalid tool_call_request structure: {tool_call_request}")
                        # Hatalı aracı atla veya bir hata sonucu ekle
                        tool_execution_results.append({
                            "role": "tool",
                            "tool_call_id": tool_call_id or f"error_tc_{uuid.uuid4()}",
                            "name": tool_name or "unknown_tool",
                            "content": json.dumps({"error": "Invalid tool call structure from LLM."})
                        })
                        continue
                    
                    try:
                        tool_args_dict = json.loads(tool_args_str)
                        function_name = "call_service"
                        # GptPackage üzerinden servislere ulaş
                        if self.gpt_package:
                            for service in self.gpt_package.services.all():
                                if service.key == tool_name and service.is_active and service.default_params:
                                    # Default parametreleri tool_args_dict ile birleştir
                                    # default_params öncelikli olmasın diye önce onu kopyalayıp üzerine tool_args_dict yazıyoruz
                                    merged_args = service.default_params.copy()
                                    merged_args.update(tool_args_dict)
                                    function_name = service.function_name
                                    tool_args_dict = merged_args
                                    break
                        else:
                            print(f"GptPackage not found for tool {tool_name}")
                            logger.error(f"GptPackage not found for tool {tool_name}")

                        logger.info(f"Executing tool: {tool_name} with args: {tool_args_dict}")
                        result = await sync_to_async(run_tool)(function_name, tool_name, tool_args_dict, user_profile=self.user_profile)
                        tool_execution_results.append({
                            "role": "tool", 
                            "tool_call_id": tool_call_id,
                            "name": tool_name,
                            "content": json.dumps(result) # Araç sonucu JSON string olmalı
                        })
                    except json.JSONDecodeError:
                        logger.error(f"Failed to decode arguments for tool {tool_name}: {tool_args_str}")
                        tool_execution_results.append({
                            "role": "tool",
                            "tool_call_id": tool_call_id,
                            "name": tool_name,
                            "content": json.dumps({"error": f"Invalid arguments format: {tool_args_str}"})
                        })
                    except Exception as e:
                        logger.error(f"Error running tool {tool_name}: {e}", exc_info=True)
                        tool_execution_results.append({
                            "role": "tool",
                            "tool_call_id": tool_call_id,
                            "name": tool_name,
                            "content": json.dumps({"error": f"Tool execution failed: {str(e)}"})
                        })
                
                current_message_history.extend(tool_execution_results) # Araç sonuçlarını geçmişe ekle
                tool_cycle_count += 1
                # Döngü devam edecek, LLM'e güncellenmiş geçmişle tekrar sorulacak.
            
            # While döngüsü bitti (ya araç kalmadı ya da MAX_TOOL_CYCLES'a ulaşıldı)
            if tool_cycle_count >= MAX_TOOL_CYCLES:
                logger.warning("Maximum tool call cycles reached.")
                # Kullanıcıya bilgi verilebilir.

            # En son bir "stream bitti" mesajı gönderelim (eğer dispatcher zaten göndermediyse)
            # Bu, frontend'in yükleme göstergesini vs. kaldırmasına yardımcı olabilir.
            await self.send(text_data=json.dumps({
                "type": "assistant_stream_finalized" 
                # "final_content" gibi bir alan da eklenebilir, ama stream ile gönderdik zaten.
            }))

            # Nihai yanıtı ve aksiyonları kaydet
            if full_assistant_response_content or final_actions_for_ui: # Eğer bir yanıt veya aksiyon varsa
                await Message.objects.acreate(
                    conversation=self.conversation,
                    sender='gpt', 
                    content=full_assistant_response_content.strip(), # Temizlenmiş metin
                    gpt_package=self.gpt_package,
                    actions=final_actions_for_ui if final_actions_for_ui else None
                )
                # Conversation'ın updated_at alanını güncelle
                self.conversation.updated_at = datetime.datetime.now(datetime.timezone.utc)
                await self.conversation.asave(update_fields=['updated_at'])

            if final_actions_for_ui:
                await self.send(text_data=json.dumps({
                    "type": "ui_actions", # Frontend'in bekleyeceği özel bir tip
                    "actions": final_actions_for_ui
                }))

        except Exception as e:
            logger.error(f"Error in generate_response_from_dispatcher: {e}", exc_info=True)
            await self.send_error(f"Yanıt üretirken bir hata oluştu: {str(e)}")

    async def evaluate_gpt_package(self, user_input: str, conversation_summary: Optional[str] = None) -> bool:
        """
        1. Context ve tool uygunluğunu kontrol eder.
        2. Gerekirse semantic arama ile yeni bir GPT paketi önerir.
        3. Uygun paket yoksa kullanıcıya kapsam dışı mesajı döner.
        """
        # 1. Context uygunluğu kontrolü
        if not self.is_context_compatible(self.gpt_package, conversation_summary):
            # Uygun değilse semantic arama ile yeni paket bul
            return await self.switch_gpt_package_by_semantic(user_input)

        # 2. Tool uygunluğu kontrolü
        required_tool = self.extract_required_tool(user_input)
        if required_tool and not self.gpt_package_has_tool(self.gpt_package, required_tool):
            # Gerekli tool yoksa semantic arama ile yeni paket bul
            return await self.switch_gpt_package_by_semantic(user_input, required_tool)

        # Her şey uygunsa devam et
        return True

    def is_context_compatible(self, gpt_package, conversation_summary):
        """
        Burada context ve gpt_package uyumluluğu kontrol edilir.
        Örneğin: conversation_summary, gpt_package'ın supported_contexts veya capabilities'inde mi?
        Şimdilik her zaman True döndürülüyor.
        """
        # TODO: Gerçek context uyumluluk kontrolü eklenebilir.
        return True

    def extract_required_tool(self, user_input):
        """
        Kullanıcı mesajından hangi tool gerektiğini çıkarır (intent extraction, keyword, vs.).
        Örneğin: "tabloyu özetle" -> "table_summarizer"
        Şimdilik None döndürülüyor.
        """
        # TODO: Gelişmiş intent extraction eklenebilir.
        return None

    def gpt_package_has_tool(self, gpt_package, tool_key):
        """
        gpt_package.services.all() içinde tool_key var mı?
        """
        if not gpt_package or not hasattr(gpt_package, 'services'):
            return False
        return any(service.key == tool_key for service in gpt_package.services.all())

    async def switch_gpt_package_by_semantic(self, user_input, required_tool=None):
        """
        find_best_gpt_package fonksiyonunu çağırır, gerekirse required_tool'u da dikkate alır.
        """
        # TODO: required_tool parametresi semantic aramaya entegre edilebilir.
        best_package_info = await sync_to_async(find_best_gpt_package)(user_input, self.user_profile)
        if best_package_info:
            best_package, score = best_package_info
            if best_package and score > self.similarity_threshold:
                self.gpt_package = best_package
                self.conversation = await self.get_or_create_conversation_for_gpt_package(force_new=True)
                await self.send(text_data=json.dumps({
                    "type": "gpt_package_switched",
                    "new_gpt_package_id": str(self.gpt_package.id),
                    "new_gpt_package_name": self.gpt_package.name,
                    "conversation_id": str(self.conversation.id)
                }))
                return True
        await self.send_error("Bu konu mevcut paketlerle yanıtlanamıyor.")
        return False

    # `change_context` ve `change_gpt_package` (veya `check_and_switch_gpt_package`)
    # metodları, konuşma bağımsız hafıza ve dinamik GPT geçişleri için daha sonra
    # detaylı olarak implemente edilebilir.
    # Şimdilik, `get_or_create_conversation_for_gpt_package` ile
    # her GPT paketi için (veya her "new_conversation" isteği için)
    # yeni/ayrı bir Conversation objesi kullanıyoruz.

    # async def check_and_switch_gpt_package(self, message_content: str):
    #     """ Kullanıcının niyetine göre GPT paketini değiştirmeye çalışır. """
    #     if not self.user_profile or not self.gpt_package or not self.conversation:
    #         return

    #     # `find_best_gpt_package` asenkron değil, sync_to_async ile sarmala
    #     # Ayrıca, bu fonksiyonun girdisi (message_content) ve GPT paketlerinin
    #     # tanımları (description) vektörleri üzerinden çalışır.
    #     best_package_info = await sync_to_async(find_best_gpt_package)(message_content)
    #     if best_package_info:
    #         best_package, score = best_package_info
    #         logger.debug(f"Semantic search for GptPackage: Best match '{best_package.name if best_package else 'None'}' with score {score}")
    #         # Belirli bir eşik değerinin üzerindeyse ve mevcut paketten farklıysa geçiş yap
    #         # Örneğin, score > 0.80 and (not self.gpt_package or best_package.id != self.gpt_package.id)
    #         if best_package and score > 0.75 and (self.gpt_package.id != best_package.id): # Eşik değeri ayarlanabilir
    #             logger.info(f"Switching GptPackage from {self.gpt_package.name} to {best_package.name} based on semantic score {score}.")
    #             self.gpt_package = best_package
    #             # Yeni GPT paketi için yeni bir konuşma başlat veya mevcut konuşmanın paketini güncelle
    #             self.conversation = await self.get_or_create_conversation_for_gpt_package(force_new=True) # Yeni paket = yeni konuşma
                 
    #             await self.send(text_data=json.dumps({
    #                 "type": "gpt_package_switched",
    #                 "new_gpt_package_id": str(self.gpt_package.id),
    #                 "new_gpt_package_name": self.gpt_package.name,
    #                 "conversation_id": str(self.conversation.id)
    #             }))

    # --- KONUŞMA KONTEXTİ ÖZETLEME ve QDRANT'A KAYIT ---
    async def maybe_update_conversation_summary(self):
        # Son N mesajı al, özetle, embedding'le, Qdrant'a kaydet
        messages = await self.prepare_message_history(limit=20)
        if len(messages) < self.context_summary_trigger:
            return  # Yeterli mesaj yoksa özetleme yapma
        context_text = " ".join([m["content"] for m in messages if m["content"]])
        # LLM ile özetleme (örnek, burada basitçe ilk 300 karakteri alıyoruz, gerçek özetleme için LLM çağrısı eklenebilir)
        summary = context_text[:300] + ("..." if len(context_text) > 300 else "")
        embedding = await sync_to_async(semantic.get_embedding)(summary)
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
        payload = {
            "id": f"{self.conversation.id}_{timestamp}",
            "conversation_id": str(self.conversation.id),
            "user_profile_id": str(self.user_profile.id),
            "summary": summary,
            "timestamp": timestamp
        }
        await sync_to_async(semantic.add_to_qdrant)(
            collection_name="conversation_contexts",
            text=summary,
            payload=payload
        )
        self.conversations_pool[self.conversation.id] = {"summary": summary, "embedding": embedding, "timestamp": timestamp}

    # --- QDRANT'TAN HAFIZA ARAMASI ---
    async def search_memory_contexts(self, query: str):
        query_embedding = await sync_to_async(semantic.get_embedding)(query)
        filter_dict = {"user_profile_id": str(self.user_profile.id)}
        results = await sync_to_async(semantic.search_qdrant)(
            collection_name="conversation_contexts",
            text=query,
            filter=filter_dict,
            limit=self.memory_context_limit
        )
        memory_contexts = []
        for r in results:
            payload = r.payload
            memory_contexts.append({
                "summary": payload.get("summary", ""),
                "timestamp": payload.get("timestamp", "")
            })
        return memory_contexts

    # --- LLM YANITI ÜRETME (system prompt ile) ---
    async def generate_response_from_dispatcher_with_system_prompt(self, history_messages: List[Dict[str, Any]], system_prompt: str):
        if not self.user_profile or not self.gpt_package or not self.conversation:
            logger.error("Cannot generate response: user_profile, gpt_package, or conversation is not set.")
            await self.send_error("Yanıt üretilemedi: Gerekli oturum bilgileri eksik.")
            return

        current_message_history = list(history_messages)
        full_assistant_response_content = ""
        final_actions_for_ui = []
        MAX_TOOL_CYCLES = 5
        tool_cycle_count = 0

        try:
            while tool_cycle_count < MAX_TOOL_CYCLES:
                logger.debug(f"Tool cycle {tool_cycle_count + 1}. History length: {len(current_message_history)}")
                streamed_content_in_this_llm_call = False
                llm_requested_tool_calls = []

                # system prompt'u ilk mesaja prepend et
                processed_messages = [{"role": "system", "content": system_prompt}] + current_message_history

                async for response_part in llm_dispatcher.call_model(
                    self.gpt_package,
                    self.user_profile,
                    processed_messages
                ):
                    event_type = response_part.get("type")
                    event_data = response_part.get("data")

                    if event_type == "content_chunk":
                        full_assistant_response_content += event_data
                        streamed_content_in_this_llm_call = True
                        await self.send(text_data=json.dumps({
                            "type": "assistant_message_chunk",
                            "chunk": event_data
                        }))
                    elif event_type == "tool_calls_ready":
                        llm_requested_tool_calls = event_data
                        logger.info(f"LLM requested {len(llm_requested_tool_calls)} tools to be called.")
                    elif event_type == "stream_end":
                        logger.debug(f"LLM stream ended. Finish reason: {event_data.get('finish_reason')}")
                        current_ui_actions = llm_dispatcher.parse_actions(full_assistant_response_content)
                        if current_ui_actions:
                            final_actions_for_ui.extend(current_ui_actions)
                            full_assistant_response_content = llm_dispatcher.process_model_response_text_for_ui(full_assistant_response_content)
                        break
                    elif event_type == "error":
                        logger.error(f"Error from llm_dispatcher: {event_data}")
                        await self.send_error(f"Model hatası: {event_data}")
                        return

                if not llm_requested_tool_calls:
                    logger.debug("No tool calls requested by LLM in this cycle. Ending tool loop.")
                    break

                assistant_message_for_history = {
                    "role": "assistant",
                    "content": full_assistant_response_content if streamed_content_in_this_llm_call else None,
                    "tool_calls": llm_requested_tool_calls
                }
                current_message_history.append(assistant_message_for_history)
                full_assistant_response_content = ""

                tool_execution_results = []
                for tool_call_request in llm_requested_tool_calls:
                    tool_name = tool_call_request.get("function", {}).get("name")
                    tool_args_str = tool_call_request.get("function", {}).get("arguments")
                    tool_call_id = tool_call_request.get("id")

                    if not tool_name or not tool_args_str or not tool_call_id:
                        logger.error(f"Invalid tool_call_request structure: {tool_call_request}")
                        tool_execution_results.append({
                            "role": "tool",
                            "tool_call_id": tool_call_id or f"error_tc_{uuid.uuid4()}",
                            "name": tool_name or "unknown_tool",
                            "content": json.dumps({"error": "Invalid tool call structure from LLM."})
                        })
                        continue
                    try:
                        tool_args_dict = json.loads(tool_args_str)
                        function_name = "call_service"
                        if self.gpt_package:
                            for service in self.gpt_package.services.all():
                                if service.key == tool_name and service.is_active and service.default_params:
                                    merged_args = service.default_params.copy()
                                    merged_args.update(tool_args_dict)
                                    function_name = service.function_name
                                    tool_args_dict = merged_args
                                    break
                        else:
                            logger.error(f"GptPackage not found for tool {tool_name}")
                        logger.info(f"Executing tool: {tool_name} with args: {tool_args_dict}")
                        result = await sync_to_async(run_tool)(function_name, tool_name, tool_args_dict, user_profile=self.user_profile)
                        tool_execution_results.append({
                            "role": "tool",
                            "tool_call_id": tool_call_id,
                            "name": tool_name,
                            "content": json.dumps(result)
                        })
                    except json.JSONDecodeError:
                        logger.error(f"Failed to decode arguments for tool {tool_name}: {tool_args_str}")
                        tool_execution_results.append({
                            "role": "tool",
                            "tool_call_id": tool_call_id,
                            "name": tool_name,
                            "content": json.dumps({"error": f"Invalid arguments format: {tool_args_str}"})
                        })
                    except Exception as e:
                        logger.error(f"Error running tool {tool_name}: {e}", exc_info=True)
                        tool_execution_results.append({
                            "role": "tool",
                            "tool_call_id": tool_call_id,
                            "name": tool_name,
                            "content": json.dumps({"error": f"Tool execution failed: {str(e)}"})
                        })
                current_message_history.extend(tool_execution_results)
                tool_cycle_count += 1

            if tool_cycle_count >= MAX_TOOL_CYCLES:
                logger.warning("Maximum tool call cycles reached.")

            await self.send(text_data=json.dumps({
                "type": "assistant_stream_finalized"
            }))

            if full_assistant_response_content or final_actions_for_ui:
                await Message.objects.acreate(
                    conversation=self.conversation,
                    sender='gpt',
                    content=full_assistant_response_content.strip(),
                    gpt_package=self.gpt_package,
                    actions=final_actions_for_ui if final_actions_for_ui else None
                )
                self.conversation.updated_at = datetime.datetime.now(datetime.timezone.utc)
                await self.conversation.asave(update_fields=['updated_at'])

            if final_actions_for_ui:
                await self.send(text_data=json.dumps({
                    "type": "ui_actions",
                    "actions": final_actions_for_ui
                }))

        except Exception as e:
            logger.error(f"Error in generate_response_from_dispatcher_with_system_prompt: {e}", exc_info=True)
            await self.send_error(f"Yanıt üretirken bir hata oluştu: {str(e)}")