# hexense_core/consumers.py

from channels.generic.websocket import AsyncWebsocketConsumer
import json
import datetime
import uuid
import logging # Logging ekleyelim
from typing import List, Dict, Any, Optional
from asgiref.sync import sync_to_async
from .models import Conversation, Message, UserProfile, GptPackage
from .semantic import find_best_gpt_package # Bu hala kullanılacak
from .tools import run_tool # Araçları çalıştırmak için
from hexense_core import llm_dispatcher # Yeni dispatcher'ımızı import edelim


logger = logging.getLogger(__name__)

class ChatConsumer(AsyncWebsocketConsumer):
    similarity_threshold = 0.85 # Bu değer config'den alınabilir

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
                    self.user_profile = await UserProfile.objects.select_related('company', 'role', 'department').aget(id=profile_id, user=self.user)
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
                    self.gpt_package = await GptPackage.objects.select_related('model').aget(id=gpt_package_id)
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

                # Eğer aktif bir konuşma yoksa veya GPT paketi değiştiyse,
                # uygun bir konuşma bul veya oluştur.
                if not self.conversation or (self.conversation.gpt_package != self.gpt_package):
                    self.conversation = await self.get_or_create_conversation_for_gpt_package()

                # Dinamik GPT paketi değiştirme mantığı (opsiyonel, şimdilik devre dışı bırakılabilir)
                # await self.check_and_switch_gpt_package(message_content)
                # Eğer GPT paketi değiştiyse, self.conversation da güncellenmiş olmalı.

                # Kullanıcı mesajını veritabanına kaydet
                await Message.objects.acreate(
                    conversation=self.conversation,
                    sender='user',
                    content=message_content,
                    gpt_package=self.gpt_package # Hangi paketle gönderildiği bilgisi
                )
                
                # LLM'e göndermek için mesaj geçmişini hazırla
                history_messages = await self.prepare_message_history()
                history_messages.append({"role": "user", "content": message_content})

                # Yanıtı generate_response ile al ve stream et
                await self.generate_response_from_dispatcher(history_messages)

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
                user_profile=self.user_profile,
                gpt_package=self.gpt_package,
                # topic ve topic_embedding başlangıçta boş olabilir veya ilk mesajdan sonra güncellenebilir.
            )
            logger.info(f"Forced new conversation {conv.id} for UserProfile {self.user_profile.id} and GptPackage {self.gpt_package.name}")
            return conv

        # Son güncellenen, bu profile ve pakete ait konuşmayı bulmaya çalış
        # Bu mantık, kullanıcının aynı paketle devam ettiği sürece aynı konuşmada kalmasını sağlar.
        # Daha karmaşık "context switching" için bu kısım geliştirilebilir.
        conv = await Conversation.objects.filter(
            user_profile=self.user_profile,
            gpt_package=self.gpt_package
        ).order_by('-updated_at').afirst()

        if not conv:
            conv = await Conversation.objects.acreate(
                user_profile=self.user_profile,
                gpt_package=self.gpt_package
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
                        logger.info(f"Executing tool: {tool_name} with args: {tool_args_dict}")
                        # `run_tool` fonksiyonu UserProfile bekliyordu, güncelleyelim.
                        # `run_tool`'un `user_profile` parametresini alacak şekilde güncellenmesi gerekebilir.
                        # `hexense_core/utils.py` içindeki `run_tool`'a `user_profile` eklenmeli.
                        # Şimdilik `run_tool`'un `user_profile` aldığını varsayıyorum.
                        result = await sync_to_async(run_tool)(tool_name, tool_args_dict, user_profile=self.user_profile)
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