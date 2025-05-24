import requests
from .semantic import find_best_gpt_package


def call_service(endpoint: str, payload: dict = None, method: str = "GET", headers: dict = None, data_path: str = None, verify: bool = True) -> dict:
    print(f"call_service: endpoint={endpoint}, method={method}, payload={payload}, headers={headers}, data_path={data_path}")
    payload = payload or {}
    headers = headers or {}
    try:
        if method.upper() == "GET":
            print(f"Making GET request to {endpoint}")
            response = requests.get(endpoint, params=payload, headers=headers, verify=verify)
        else: # POST, PUT, etc.
            print(f"Making {method.upper()} request to {endpoint}")
            response = requests.request(method.upper(), endpoint, json=payload, headers=headers,verify=verify)

        print(f"Response status code: {response.status_code}")
        response.raise_for_status() # HTTP hataları için exception fırlatır

        json_response = response.json()
        print(f"Response JSON: {json_response}")

        if data_path: # Eğer yanıttan belirli bir alan çekilecekse
            print(f"Extracting data using path: {data_path}")
            # Basit bir data_path çözümlemesi, örn: "data.attributes.text"
            keys = data_path.split('.')
            data = json_response
            for key in keys:
                print(f"Accessing key: {key}")
                if isinstance(data, dict) and key in data:
                    data = data[key]
                elif isinstance(data, list) and key.isdigit() and int(key) < len(data):
                    data = data[int(key)]
                else:
                    print(f"Data path '{data_path}' not found in response")
                    return {"status": "error", "message": f"Data path '{data_path}' not found in response."}
            print(f"Extracted data: {data}")
            return {"status": "success", "data": data} # Sadece ilgili veriyi döndür
        else:
            return {"status": "success", "data": json_response} # Tüm JSON yanıtını döndür

    except requests.RequestException as e:
        print(f"Request error: {str(e)}")
        return {"status": "error", "message": str(e)}
    except ValueError as e: # JSON decode hatası için
        print(f"JSON decode error: {str(e)}")
        return {"status": "error", "message": f"JSON decode error: {str(e)}"}

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
