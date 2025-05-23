import uuid
import os
f# hexense_core/utils.py
# def run_tool(function_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
# Şöyle olmalı (eğer UserProfile gerekiyorsa):
from .models import UserProfile # Gerekirse import edin
from typing import Any, Dict, Optional

def run_tool(function_name: str, args: Dict[str, Any], user_profile: Optional[UserProfile] = None) -> Dict[str, Any]:
    import hexense_core.tools as tools 
    func = getattr(tools, function_name, None)

    if not callable(func):
        raise ValueError(f"Fonksiyon '{function_name}' tools.py içinde tanımlı değil.")

    try:
        return func(**args)
    except Exception as e:
        return {
            "status": "error",
            "message": f"Fonksiyon çalıştırılırken hata oluştu: {str(e)}"
        }


def upload_to_folder(instance, filename, folder_name='uploads'):
    """
    Dosyaları belirli bir klasör altında benzersiz UUID ile kaydeder.
    """
    ext = filename.split('.')[-1]
    filename = f"{uuid.uuid4()}.{ext}"
    return os.path.join(folder_name, filename)

def avatar_upload_path(instance, filename):
    return upload_to_folder(instance, filename, folder_name='avatars')

def company_logo_upload_path(instance, filename):
    return upload_to_folder(instance, filename, folder_name='company_logos')

