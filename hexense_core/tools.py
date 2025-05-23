import requests
from .semantic import find_best_gpt_package

# 1️⃣ Harici bir servisi çağıran genel amaçlı fonksiyon
def call_service(endpoint: str, payload: dict, method: str = "POST", headers: dict = None) -> dict:
    """
    Verilen endpoint'e HTTP isteği yapar.
    """
    headers = headers or {}
    try:
        if method.upper() == "GET":
            response = requests.get(endpoint, params=payload, headers=headers)
        else:
            response = requests.post(endpoint, json=payload, headers=headers)

        response.raise_for_status()
        return {
            "status": "success",
            "data": response.json()
        }
    except requests.RequestException as e:
        return {
            "status": "error",
            "message": str(e)
        }

# 2️⃣ GPT'yi değiştirme isteği oluşturan fonksiyon
def switch_gpt(intent_description: str, **kwargs):
    """
    Kullanıcının niyetine göre uygun GPTPackage'ı bulur ve ona yönlendirir.
    """
    if not intent_description:
        return {
            "error": "Kullanıcı amacı (intent_description) sağlanmadı."
        }

    try:
        best_package, score = find_best_gpt_package(intent_description)
        return {
            "message": f"'{best_package.name}' GPT yardımcısına geçiliyor.",
            "target_package_id": str(best_package.id),
            "matched_score": round(score, 3),
            "matched_description": best_package.description
        }
    except Exception as e:
        return {
            "error": f"GPT seçimi sırasında hata oluştu: {str(e)}"
        }
