import json
from typing import List, Dict, Optional, Any, Union
from .models import GptModel, GptPackage, Message
from .utils import run_tool
from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline
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
    """Standard response format for all model calls"""
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

def validate_api_key(company, provider: str) -> None:
    """Validate API key for the given provider"""
    api_key = getattr(company, f"{provider}_api_key", None)
    if not api_key:
        raise APIKeyError(f"{provider.upper()} API key is not configured for the company")
    return api_key

def parse_tool_calls(text: str) -> List[Dict[str, Any]]:
    """
    Parse tool calls from model response text.
    Looks for JSON-like structures in the text.
    """
    tool_calls = []
    try:
        # Try to find JSON-like structures in the text
        json_pattern = r'\{[^{}]*\}'
        matches = re.finditer(json_pattern, text)
        
        for match in matches:
            try:
                json_str = match.group()
                data = json.loads(json_str)
                if isinstance(data, dict) and "tool" in data and "parameters" in data:
                    tool_calls.append(data)
            except json.JSONDecodeError:
                continue
    except Exception as e:
        logger.error(f"Error parsing tool calls: {str(e)}")
    
    return tool_calls

def parse_actions(text: str) -> List[Dict[str, Any]]:
    """
    Parse UI actions from model response text.
    Looks for action markers and JSON structures.
    """
    actions = []
    try:
        # Look for action markers in the text
        action_pattern = r'\[ACTION\](.*?)\[/ACTION\]'
        matches = re.finditer(action_pattern, text, re.DOTALL)
        
        for match in matches:
            try:
                action_text = match.group(1).strip()
                action_data = json.loads(action_text)
                if isinstance(action_data, dict):
                    actions.append(action_data)
            except json.JSONDecodeError:
                continue
    except Exception as e:
        logger.error(f"Error parsing actions: {str(e)}")
    
    return actions

def process_model_response(text: str) -> ModelResponse:
    """
    Process raw model response text into standardized format.
    Extracts tool calls and actions, and cleans up the content.
    """
    # Extract tool calls and actions
    tool_calls = parse_tool_calls(text)
    actions = parse_actions(text)
    
    # Clean up the content by removing tool calls and actions
    content = text
    for tool_call in tool_calls:
        content = content.replace(json.dumps(tool_call), "")
    for action in actions:
        content = content.replace(f"[ACTION]{json.dumps(action)}[/ACTION]", "")
    
    # Clean up extra whitespace and newlines
    content = re.sub(r'\n\s*\n', '\n\n', content.strip())
    
    return ModelResponse(
        content=content,
        actions=actions,
        tool_calls=tool_calls
    )

def call_model(gpt_package, user_profile, messages: List[Dict]) -> Dict:
    """
    Dispatch the message to the appropriate model based on the provider.
    Returns a standardized response format.
    """
    print(gpt_package)
    try:
        if not messages:
            raise ValidationError("Messages list cannot be empty")
        gpt_model = gpt_package.model if gpt_package.model else None
        if gpt_model.is_local:
            response = call_local_model(gpt_package, user_profile, messages)
        else:
            provider = gpt_model.provider.lower()
            if provider == "openai":
                response = call_openai_model(gpt_package, user_profile, messages)
            elif provider == "anthropic":
                response = call_anthropic_model(gpt_package, user_profile, messages)
            elif provider == "gemini":
                response = call_gemini_model(gpt_package, user_profile, messages)
            else:
                raise ModelError(f"Unsupported provider: {provider}")
        
        return response.to_dict()
    except Exception as e:
        logger.error(f"Error in call_model: {str(e)}")
        print(e.__traceback__)
        return ModelResponse(
            content="Üzgünüm, bir hata oluştu.",
            error=str(e)
        ).to_dict()

def get_gpt_package_services(gpt_package):
    """
    Converts GPT package services into a format suitable for ChatGPT's tools/functions.
    Returns a list of tool definitions that can be used with the OpenAI API.
    """
    tools = []
    
    for service in gpt_package.services.filter(is_active=True):
        tool = {
            "type": "function",
            "function": {
                "name": service.key,
                "description": service.description,
                "parameters": {
                    "type": "object",
                    "properties": service.input_schema,
                    "required": [key for key, value in service.input_schema.items() 
                               if value.get("required", False)]
                }
            }
        }
        
        if service.output_schema:
            tool["function"]["output_schema"] = service.output_schema
            
        tools.append(tool)
    
    return tools

def build_system_prompt(user_profile, gpt_package, provider=None):
    print("GPT PACKAGE", gpt_package.model.name)
    """
    Build system prompt based on user profile, GPT package and provider information.
    Includes tool definitions for non-OpenAI providers.
    
    Args:
        user: The user making the request
        gpt_package: The GPT package configuration
        provider: Optional provider name for specific formatting
        
    Returns:
        str: The formatted system prompt
    """

    # Safely get user information with fallbacks
    username = user_profile.user.get_full_name() or user_profile.user.username
    gpt_preferences = getattr(user_profile, 'gpt_preferences', '') if user_profile else ""
    work_experience = getattr(user_profile, 'work_experience_notes', '') if user_profile else ""

    # Safely get role information
    role = getattr(user_profile.role, 'name', 'Tanımsız') if user_profile and user_profile.role else "Tanımsız"
    role_desc = getattr(user_profile.role, 'description', '') if user_profile and user_profile.role else ""

    # Safely get department information
    department = getattr(user_profile.department, 'name', 'Tanımsız') if user_profile and user_profile.department else "Tanımsız"
    department_desc = getattr(user_profile.department, 'description', '') if user_profile and user_profile.department else ""

    # Safely get company information
    company = getattr(user_profile.company, 'name', 'Tanımsız') if user_profile and user_profile.company else "Tanımsız"
    company_desc = getattr(user_profile.company, 'description', '') if user_profile and user_profile.company else ""

    gpt_info = gpt_package.description or ""

    # Get today's date and time
    now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    # Get last user action/message timestamp
    last_action = Message.objects.filter(conversation__user_profile=user_profile, sender='user').order_by('-timestamp').first()
    last_action_str = last_action.timestamp.strftime('%Y-%m-%d %H:%M:%S') if last_action else 'Yok'

    # Conditional info blocks
    company_block = f"- Departmanı: {department} → {department_desc}\n- Şirketi: {company} → {company_desc}" if getattr(gpt_package, 'include_company_info', False) else ""
    personal_block = f"- İş Deneyimi ve Uzmanlık Alanları:\n\"\"\"{work_experience}\"\"\"" if getattr(gpt_package, 'include_personal_info', False) else ""

    # Get available tools for the package
    tools = get_gpt_package_services(gpt_package)
    tools_description = ""
    
    if tools and provider in ["anthropic", "gemini", "local"]:
        tools_description = "\n\n🔧 Kullanılabilir Fonksiyonlar:\n"
        for tool in tools:
            tool_name = tool.get("function", {}).get("name", "")
            tool_desc = tool.get("function", {}).get("description", "")
            tool_params = tool.get("function", {}).get("parameters", {}).get("properties", {})
            
            tools_description += f"\n- {tool_name}: {tool_desc}\n"
            if tool_params:
                tools_description += "  Parametreler:\n"
                for param_name, param_info in tool_params.items():
                    param_desc = param_info.get("description", "")
                    param_type = param_info.get("type", "")
                    tools_description += f"    - {param_name} ({param_type}): {param_desc}\n"

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
{tools_description}
""".strip()

    # Claude & Gemini için özel yönlendirme
    if provider in ["anthropic", "gemini"]:
        base_prompt += """

🧠 Sadece aşağıdaki JSON formatında çıktı üret:
{
  "tool": "kullanılacak_tool_adi",
  "parameters": {
    "param1": "deger1",
    "param2": "deger2"
  }
}
🔒 Açıklama, yorum veya başka metin ekleme. Sadece geçerli JSON döndür.

📝 UI aksiyonları için:
[ACTION]{
  "type": "action_type",
  "parameters": {
    "param1": "deger1",
    "param2": "deger2"
  }
}[/ACTION]
"""

    # Ek system_prompt varsa paketten dahil et
    if gpt_package.system_prompt:
        base_prompt += f"\n\n📘 Sistem Ek Açıklaması:\n{gpt_package.system_prompt}"

    return base_prompt

def build_prompt_text(messages: List[Dict]) -> str:
    """
    Build a text prompt from a list of messages.
    
    Args:
        messages: List of message dictionaries
        
    Returns:
        str: Formatted prompt text
    """
    return "\n".join(
        f"{m['role'].capitalize()}: {m['content']}" for m in messages
    ) + "\nAssistant:"

def build_local_prompt(messages: List[Dict]) -> str:
    """
    Build a prompt for local models with emoji indicators.
    
    Args:
        messages: List of message dictionaries
        
    Returns:
        str: Formatted prompt text with emoji indicators
    """
    prompt = ""
    for msg in messages:
        role = msg["role"]
        content = msg["content"]
        if role == "system":
            prompt += f"[Sistem Notu]: {content}\n"
        elif role == "user":
            prompt += f"👤: {content}\n"
        elif role == "assistant":
            prompt += f"🤖: {content}\n"
    prompt += "🤖: "  # LLM burada devam etsin
    return prompt

def call_openai_model(gpt_package, user_profile, messages) -> ModelResponse:
    print(gpt_package)
    try:
        tools = get_gpt_package_services(gpt_package)
        gpt_model = gpt_package.model if gpt_package.model else None
        system_prompt = build_system_prompt(user_profile, gpt_package, provider="openai")
        messages = [{"role": "system", "content": system_prompt}] + messages

        api_key = validate_api_key(user_profile.company, "openai")
        openai.api_key = api_key

        history_messages = messages.copy()
        max_iterations = 5
        current_iteration = 0
        final_response = None

        while current_iteration < max_iterations:
            try:
                response = openai.chat.completions.create(
                    model=gpt_model.name,
                    messages=history_messages,
                    temperature=0.7,
                    tools=tools or None,
                    tool_choice="auto" if tools else None
                )

                message = response.choices[0].message
                if not message.tool_calls:
                    return process_model_response(message.content)

                tool_responses = []
                for tool_call in message.tool_calls:
                    try:
                        result = run_tool(
                            tool_name=tool_call.function.name,
                            arguments=tool_call.function.arguments,
                            user_profile=user_profile
                        )
                        tool_responses.append({
                            "tool_call_id": tool_call.id,
                            "role": "tool",
                            "name": tool_call.function.name,
                            "content": json.dumps(result)
                        })
                    except Exception as e:
                        logger.error(f"Tool execution error: {str(e)}")
                        tool_responses.append({
                            "tool_call_id": tool_call.id,
                            "role": "tool",
                            "name": tool_call.function.name,
                            "content": json.dumps({"error": str(e)})
                        })

                history_messages.append({
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": t.id,
                            "type": "function",
                            "function": {
                                "name": t.function.name,
                                "arguments": t.function.arguments
                            }
                        } for t in message.tool_calls
                    ]
                })

                history_messages.extend(tool_responses)
                current_iteration += 1

            except openai.APIError as e:
                logger.error(f"OpenAI API error: {str(e)}")
                raise ModelError(f"OpenAI API error: {str(e)}")

        return ModelResponse(
            content="İşlem tamamlanamadı.",
            error="Maximum iteration limit reached"
        )

    except Exception as e:
        logger.error(f"Unexpected error in call_openai_model: {str(e)}")
        raise LLMDispatcherError(f"Error in OpenAI model call: {str(e)}")

def call_anthropic_model(gpt_package, user_profile, messages) -> ModelResponse:
    try:
        api_key = validate_api_key(user_profile.company, "claude")
        client = anthropic.Anthropic(api_key=api_key)
        system_prompt = build_system_prompt(user_profile, gpt_package, provider="anthropic")
        gpt_model = gpt_package.model if gpt_package.model else None
        content = [{"role": m["role"], "content": m["content"]} for m in messages]

        response = client.messages.create(
            model=gpt_model.name,
            system=system_prompt,
            messages=content,
            max_tokens=1000
        )
        
        return process_model_response(response.content[0].text)
    except Exception as e:
        logger.error(f"Unexpected error in call_anthropic_model: {str(e)}")
        raise LLMDispatcherError(f"Error in Anthropic model call: {str(e)}")

def call_gemini_model(gpt_package, user_profile, messages) -> ModelResponse:
    try:
        api_key = validate_api_key(user_profile.company, "gemini")
        genai.configure(api_key=api_key)
        gpt_model = gpt_package.model if gpt_package.model else None
        system_prompt = build_system_prompt(user_profile, gpt_package, provider="gemini")
        messages = [{"role": "system", "content": system_prompt}] + messages
        model = genai.GenerativeModel(gpt_model.name)
        text_prompt = build_prompt_text(messages)
        response = model.generate_content(text_prompt)
        
        return process_model_response(response.text)
    except Exception as e:
        logger.error(f"Unexpected error in call_gemini_model: {str(e)}")
        raise LLMDispatcherError(f"Error in Gemini model call: {str(e)}")

def call_local_model(gpt_package, user_profile, messages) -> ModelResponse:
    try:
        gpt_model = gpt_package.model if gpt_package.model else None
        model_key = gpt_model.local_path or gpt_model.name

        if model_key not in LOCAL_MODEL_CACHE:
            try:
                tokenizer = AutoTokenizer.from_pretrained(model_key)
                model = AutoModelForCausalLM.from_pretrained(model_key)
                pipe = pipeline("text-generation", model=model, tokenizer=tokenizer)
                LOCAL_MODEL_CACHE[model_key] = pipe
            except Exception as e:
                logger.error(f"Error loading local model {model_key}: {str(e)}")
                raise ModelError(f"Failed to load local model: {str(e)}")
        
        system_prompt = build_system_prompt(user_profile, gpt_package, provider="local")
        prompt = system_prompt + "\n\n" + build_prompt_text(messages)
        
        try:
            result = LOCAL_MODEL_CACHE[model_key](
                prompt, 
                max_new_tokens=500, 
                do_sample=True,
                temperature=0.7,
                top_p=0.9
            )[0]["generated_text"]
            
            return process_model_response(result)
        except Exception as e:
            logger.error(f"Error generating text with local model: {str(e)}")
            raise ModelError(f"Failed to generate text: {str(e)}")
        
    except Exception as e:
        logger.error(f"Unexpected error in call_local_model: {str(e)}")
        raise LLMDispatcherError(f"Error in local model call: {str(e)}")
