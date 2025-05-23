# hexense_core/llm_dispatcher.py

import json
from typing import List, Dict, Optional, Any, Union, AsyncGenerator
from .models import GptModel, GptPackage, UserProfile, Message
from .utils import run_tool
import openai
import anthropic
import google.generativeai as genai
from django.core.exceptions import ValidationError
import logging
import re
import datetime

logger = logging.getLogger(__name__)
LOCAL_MODEL_CACHE = {}


class LLMDispatcherError(Exception):
    """Base exception for LLM dispatcher errors"""
    pass

class APIKeyError(LLMDispatcherError):
    """Raised when API key is missing or invalid"""
    pass

class ModelError(LLMDispatcherError):
    """Raised when there are issues with the model"""
    pass

class ModelResponse:
    def __init__(
        self,
        content: str,
        actions: List[Dict[str, Any]] = None,
        tool_calls: List[Dict[str, Any]] = None,
        error: Optional[str] = None
    ):
        self.content = content
        self.actions = actions or []
        self.tool_calls = tool_calls or []
        self.error = error

    def to_dict(self) -> Dict[str, Any]:
        return {
            "content": self.content,
            "actions": self.actions,
            "tool_calls": self.tool_calls,
            "error": self.error
        }

def validate_api_key(company, provider: str) -> str:
    api_key = None
    if provider == "openai":
        api_key = getattr(company, "openai_api_key", None)
    elif provider == "anthropic":
        api_key = getattr(company, "claude_api_key", None)
    elif provider == "gemini":
        api_key = getattr(company, "gemini_api_key", None)

    if not api_key:
        raise APIKeyError(f"{provider.upper()} API key is not configured for the company")
    return api_key

def parse_actions(text: str) -> List[Dict[str, Any]]:
    actions = []
    try:
        action_pattern = r'\[ACTION\](.*?)\[/ACTION\]'
        matches = re.finditer(action_pattern, text, re.DOTALL)
        for match in matches:
            try:
                action_text = match.group(1).strip()
                action_data = json.loads(action_text)
                if isinstance(action_data, dict):
                    actions.append(action_data)
            except json.JSONDecodeError:
                logger.warning(f"Could not parse action JSON: {action_text}")
                continue
    except Exception as e:
        logger.error(f"Error parsing actions: {str(e)}")
    return actions

def process_model_response_text_for_ui(text: str) -> str:
    content = text
    content = re.sub(r'\[ACTION\](.*?)\[/ACTION\]', '', content, flags=re.DOTALL)
    content = content.strip()
    return content

def get_gpt_package_services(gpt_package: GptPackage) -> List[Dict[str, Any]]:
    tools = []
    if not hasattr(gpt_package, 'services') or not hasattr(gpt_package.services, 'filter'):
        logger.warning(f"GptPackage {gpt_package.name} does not have 'services' or it's not a valid manager.")
        return tools

    try:
        for service in gpt_package.services.filter(is_active=True):
            properties = {}
            required_params = []
            if isinstance(service.input_schema, dict):
                for param_name, schema_info in service.input_schema.items():
                    if not isinstance(schema_info, dict):
                        logger.warning(f"Invalid schema_info for param {param_name} in service {service.key}. Expected dict, got {type(schema_info)}")
                        continue

                    properties[param_name] = {
                        "type": schema_info.get("type", "string"),
                        "description": schema_info.get("description", "")
                    }
                    if schema_info.get("required", False):
                        required_params.append(param_name)
            
            tool_definition = {
                "type": "function",
                "function": {
                    "name": service.key,
                    "description": service.description,
                    "parameters": {
                        "type": "object",
                        "properties": properties,
                    }
                }
            }
            if required_params:
                tool_definition["function"]["parameters"]["required"] = required_params
            
            tools.append(tool_definition)
    except Exception as e:
        logger.error(f"Error processing services for GptPackage {gpt_package.name}: {e}", exc_info=True)
    return tools


async def build_system_prompt(user_profile: UserProfile, gpt_package: GptPackage, provider: Optional[str] = None) -> str:
    username = user_profile.user.get_full_name() or user_profile.user.username
    gpt_preferences = user_profile.gpt_preferences or ""
    work_experience = user_profile.work_experience_notes or ""

    role_name = "Tanımsız"
    role_desc = ""
    if user_profile.role:
        role_name = user_profile.role.name
        role_desc = user_profile.role.description or ""

    department_name = "Tanımsız"
    department_desc = ""
    if user_profile.department:
        department_name = user_profile.department.name
        department_desc = user_profile.department.description or ""

    company_name = "Tanımsız"
    company_desc = ""
    if user_profile.company:
        company_name = user_profile.company.name
        company_desc = user_profile.company.description or ""
    
    gpt_package_description = gpt_package.description or ""
    gpt_package_name = gpt_package.name

    now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    last_user_message_obj = await Message.objects.filter(
        conversation__user_profile=user_profile,
        sender='user'
    ).order_by('-timestamp').afirst()
    last_action_str = last_user_message_obj.timestamp.strftime('%Y-%m-%d %H:%M:%S') if last_user_message_obj else 'Yok'

    company_block = ""
    if gpt_package.include_company_info: 
        company_block = f"- Departmanı: {department_name} ({department_desc})\n- Şirketi: {company_name} ({company_desc})"
    
    personal_block = ""
    if gpt_package.include_personal_info: 
        personal_block = f"- İş Deneyimi ve Uzmanlık Alanları:\n\"\"\"{work_experience}\"\"\""

    tools_description_for_prompt = ""
    tools_for_prompt = get_gpt_package_services(gpt_package)
    if provider and provider.lower() not in ["openai"] and tools_for_prompt:
        tools_description_for_prompt = "\n\n🔧 Kullanılabilir Fonksiyonlar (Araçlar):\n"
        for tool in tools_for_prompt:
            func_info = tool.get("function", {})
            tool_name = func_info.get("name", "Bilinmeyen Araç")
            tool_desc = func_info.get("description", "Açıklama yok")
            params_desc_list = []
            if "parameters" in func_info and "properties" in func_info["parameters"]:
                for param_name, param_data in func_info["parameters"]["properties"].items():
                    param_type = param_data.get("type", "bilinmiyor")
                    param_description = param_data.get("description", "")
                    is_required = param_name in func_info.get("parameters", {}).get("required", [])
                    req_str = " (zorunlu)" if is_required else ""
                    params_desc_list.append(f"    - {param_name} ({param_type}{req_str}): {param_description}")
            params_str = "\n".join(params_desc_list)
            tools_description_for_prompt += f"\n- {tool_name}: {tool_desc}\n"
            if params_str:
                tools_description_for_prompt += f"  Parametreler:\n{params_str}\n"

    base_prompt = f"""Sen Hexense platformunda '{gpt_package_name}' isimli özel amaçlı bir yapay zeka yardımcısısın.

📅 Bugünün tarihi ve saati: {now_str}
🕑 Kullanıcının bilinen son işlemi: {last_action_str}

📌 Kullanıcı profili:
- Kullanıcı adı: {username}
- Rolü: {role_name} ({role_desc})
{company_block}
- GPT Tercihleri:
\"\"\"{gpt_preferences}\"\"\"
{personal_block}

📦 Görev Tanımın ve Yeteneklerin ({gpt_package_name}):
\"\"\"{gpt_package_description}\"\"\"

🎯 Temel Hedefin:
Kullanıcının işini kolaylaştırmak, ona doğru ve etkili bilgiler sunmak, önerilerde bulunmak ve gerektiğinde onun adına tanımlanmış araçları (fonksiyonları) kullanarak işlemler başlatmak.

❗ Önemli Kurallar:
1. Güvenlik ve gizlilik kurallarına daima uy.
2. Yanıtların net, anlaşılır ve profesyonel bir dilde olmalı.
3. Eğer bir bilgiye sahip değilsen veya bir konuda emin değilsen, bunu açıkça belirt. Yanlış veya yanıltıcı bilgi verme.
4. Kullanıcıya doğrudan dosya sistemi erişimi, veritabanı sorgusu çalıştırma gibi tehlikeli işlemler yaptıramazsın. Sadece sana tanımlanmış araçları kullan.
5. Eğer araçları kullanman gerekiyorsa, bunu yap. Çıktı formatın araç çağırma için JSON olmalı (OpenAI için özel format).
6. Yanıtının sonunda, kullanıcı arayüzünde gösterilmesi gereken özel bileşenler veya yapılması gereken aksiyonlar varsa, bunları `[ACTION]{{...JSON...}}[/ACTION]` formatında belirt.
{tools_description_for_prompt}
"""
    if gpt_package.system_prompt:
        base_prompt += f"\n\n📘 Ek Sistem Talimatları ({gpt_package_name}):\n{gpt_package.system_prompt}"
    
    if provider and provider.lower() in ["anthropic", "gemini"] and tools_for_prompt:
        base_prompt += """

🧠 Araç Kullanım Çıktı Formatı (SADECE ARAÇ KULLANACAKSAN):
Aşağıdaki JSON formatında bir veya daha fazla araç çağrısı içeren bir liste döndür:
```json
[
  {
    "tool_name": "kullanilacak_arac_adi_1",
    "parameters": {
      "param1": "deger1",
      "param2": "deger2"
    }
  },
  {
    "tool_name": "kullanilacak_arac_adi_2",
    "parameters": {}
  }
]
Eğer metin yanıtı vereceksen, bu JSON formatını KULLANMA. Sadece normal metin yanıtı ver.
"""
    return base_prompt.strip()


async def call_openai_model(gpt_package: GptPackage, user_profile: UserProfile, messages: List[Dict[str, Any]]) -> AsyncGenerator[Dict[str, Any], None]:

    if not user_profile.company:
        logger.error(f"User {user_profile.user.username} does not have an associated company. Cannot retrieve OpenAI API key.")
        yield {"type": "error", "data": "User profile is not associated with a company."}
        return

    try:
        api_key = validate_api_key(user_profile.company, "openai")
    except APIKeyError as e:
        logger.error(str(e))
        yield {"type": "error", "data": str(e)}
        return

    from openai import AsyncOpenAI
    async_openai_client = AsyncOpenAI(api_key=api_key)

    gpt_model = gpt_package.model
    if not gpt_model:
        logger.error(f"GptPackage {gpt_package.name} has no GptModel associated.")
        yield {"type": "error", "data": f"GptPackage {gpt_package.name} has no GptModel."}
        return

    tools = get_gpt_package_services(gpt_package) 

    logger.debug(f"Calling OpenAI model {gpt_model.name} with {len(messages)} messages. Tools: {bool(tools)}")

    try:
        response_stream = await async_openai_client.chat.completions.create(
            model=gpt_model.name,
            messages=messages,
            tools=tools if tools else None,
            tool_choice="auto" if tools else None,
            stream=True,
            temperature=0.7, 
        )

        accumulated_tool_calls: Dict[int, Dict[str, Any]] = {}

        async for chunk in response_stream:
            delta = chunk.choices[0].delta
            finish_reason = chunk.choices[0].finish_reason

            if delta and delta.content:
                yield {"type": "content_chunk", "data": delta.content}
            
            if delta and delta.tool_calls:
                for tool_call_chunk in delta.tool_calls:
                    index = tool_call_chunk.index
                    if index not in accumulated_tool_calls:
                        accumulated_tool_calls[index] = {
                            "id": None, 
                            "type": None, 
                            "function_name": "", 
                            "function_arguments": "" 
                        }
                    
                    if tool_call_chunk.id:
                        accumulated_tool_calls[index]["id"] = tool_call_chunk.id
                    if tool_call_chunk.type:
                        accumulated_tool_calls[index]["type"] = tool_call_chunk.type

                    if tool_call_chunk.function:
                        if tool_call_chunk.function.name:
                            accumulated_tool_calls[index]["function_name"] = tool_call_chunk.function.name
                        if tool_call_chunk.function.arguments:
                            accumulated_tool_calls[index]["function_arguments"] += tool_call_chunk.function.arguments
            
            if finish_reason == "tool_calls":
                tool_calls_to_yield = []
                for index in sorted(accumulated_tool_calls.keys()):
                    tc = accumulated_tool_calls[index]
                    if not tc.get("id"):
                        logger.error(f"Tool call at index {index} missing ID in stream. accumulated_tc: {tc}")
                        continue 

                    tool_calls_to_yield.append({
                        "id": tc["id"],
                        "type": tc.get("type", "function"),
                        "function": {
                            "name": tc["function_name"],
                            "arguments": tc["function_arguments"]
                        }
                    })
                if tool_calls_to_yield:
                    yield {"type": "tool_calls_ready", "data": tool_calls_to_yield}
                accumulated_tool_calls.clear() 

            elif finish_reason == "stop":
                if accumulated_tool_calls:
                    logger.warning("Stream finished with 'stop' but there were unyielded accumulated tool calls.")
                yield {"type": "stream_end", "data": {"finish_reason": finish_reason}}
            elif finish_reason:
                logger.warning(f"Stream finished with reason: {finish_reason}")
                yield {"type": "stream_end", "data": {"finish_reason": finish_reason, "warning": "Stream finished with non-standard reason."}}


    except openai.APIError as e:
        logger.error(f"OpenAI API error: {str(e)}", exc_info=True)
        yield {"type": "error", "data": f"OpenAI API error: {str(e)}"}
    except Exception as e:
        logger.error(f"Unexpected error in call_openai_model: {str(e)}", exc_info=True)
        yield {"type": "error", "data": f"Unexpected error during OpenAI call: {str(e)}"}


async def call_anthropic_model(gpt_package: GptPackage, user_profile: UserProfile, messages: List[Dict[str, Any]]) -> AsyncGenerator[Dict[str, Any], None]:
    logger.warning("Anthropic stream and tool use is not fully implemented yet in llm_dispatcher.")
    yield {"type": "content_chunk", "data": "[Anthropic yanıtı buraya gelecek - stream implementasyonu gerekiyor]"}
    yield {"type": "stream_end", "data": {"finish_reason": "stop"}}

async def call_gemini_model(gpt_package: GptPackage, user_profile: UserProfile, messages: List[Dict[str, Any]]) -> AsyncGenerator[Dict[str, Any], None]:
    logger.warning("Gemini stream and tool use is not fully implemented yet in llm_dispatcher.")
    yield {"type": "content_chunk", "data": "[Gemini yanıtı buraya gelecek - stream implementasyonu gerekiyor]"}
    yield {"type": "stream_end", "data": {"finish_reason": "stop"}}

async def call_local_model(gpt_package: GptPackage, user_profile: UserProfile,messages: List[Dict[str, Any]]) -> AsyncGenerator[Dict[str, Any], None]:
    logger.warning("Local model stream is not implemented yet in llm_dispatcher.")
    yield {"type": "content_chunk", "data": "[Yerel model yanıtı buraya gelecek - stream implementasyonu gerekiyor]"}
    yield {"type": "stream_end", "data": {"finish_reason": "stop"}}

async def call_model(gpt_package: GptPackage, user_profile: UserProfile, messages: List[Dict[str, Any]]) -> AsyncGenerator[Dict[str, Any], None]:
    try:
        if not messages: # En azından bir kullanıcı mesajı olmalı
            logger.error("call_model called with an empty messages list.")
            raise ValidationError("Messages list cannot be empty for call_model")
        gpt_model = gpt_package.model
        if not gpt_model:
            logger.error(f"GptPackage {gpt_package.name} has no GptModel associated.")
            # ModelError fırlatmak yerine, yield ile hata objesi döndürelim ki consumer işleyebilsin.
            yield {"type": "error", "data": f"GptPackage {gpt_package.name} does not have an associated GptModel."}
            yield {"type": "stream_end", "data": {"finish_reason": "error", "details": "No GptModel in GptPackage."}}
            return # Jeneratörden çık

        system_prompt_text = await build_system_prompt(user_profile, gpt_package, provider=gpt_model.provider.lower())
        
        processed_messages = [{"role": "system", "content": system_prompt_text}] + messages
        
        provider = gpt_model.provider.lower()

        if gpt_model.is_local:
            async for chunk_data in call_local_model(gpt_package, user_profile, processed_messages):
                yield chunk_data
        elif provider == "openai":
            async for chunk_data in call_openai_model(gpt_package, user_profile, processed_messages):
                yield chunk_data
        elif provider == "anthropic":
            async for chunk_data in call_anthropic_model(gpt_package, user_profile, processed_messages):
                yield chunk_data
        elif provider == "gemini":
            async for chunk_data in call_gemini_model(gpt_package, user_profile, processed_messages):
                yield chunk_data
        else:
            logger.error(f"Unsupported provider: {provider}")
            yield {"type": "error", "data": f"Unsupported provider: {provider}"}
            yield {"type": "stream_end", "data": {"finish_reason": "error", "details": f"Unsupported provider: {provider}"}}


    except APIKeyError as e:
        logger.error(f"API Key Error in call_model: {str(e)}")
        yield {"type": "error", "data": str(e)}
        yield {"type": "stream_end", "data": {"finish_reason": "error", "details": str(e)}}
    except ModelError as e: # Bu da bizim tanımladığımız bir hata
        logger.error(f"Model Error in call_model: {str(e)}")
        yield {"type": "error", "data": str(e)}
        yield {"type": "stream_end", "data": {"finish_reason": "error", "details": str(e)}}
    except ValidationError as e:
        logger.error(f"Validation Error in call_model: {str(e)}")
        yield {"type": "error", "data": f"Input validation error: {str(e)}"}
        yield {"type": "stream_end", "data": {"finish_reason": "error", "details": f"Input validation error: {str(e)}"}}
    except Exception as e:
        logger.error(f"Unexpected error in call_model: {str(e)}", exc_info=True)
        yield {"type": "error", "data": f"An unexpected error occurred: {str(e)}"}
        yield {"type": "stream_end", "data": {"finish_reason": "error", "details": f"An unexpected error occurred: {str(e)}"}}    
    

