from hexense_core.models import GptPackage
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.http import models as qdrant_models
from typing import Tuple
import os
from hexense_core import llm_dispatcher
import asyncio

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")

_embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
qdrant_client = QdrantClient(QDRANT_URL)

def find_best_gpt_package(user_input: str, user_profile) -> Tuple[GptPackage, float]:
    """
    Kullanıcının profiline atanmış ve modeli aktif olan GPT paketleri arasında en iyi eşleşeni bulur.
    Gelecekte kullanımı olan (modeli aktif olmayan) paketleri hariç tutar.
    """
    # Kullanıcının rolüne atanmış ve modeli aktif olan paketleri bul
    allowed_packages = GptPackage.objects.filter(
        allowed_roles=user_profile.role,
        model__is_active=True
    ).distinct()
    if not allowed_packages.exists():
        return None, 0.0

    # Qdrant'ta sadece bu paketler arasında arama yapmak için filtre uygula
    # Qdrant payload'unda gpt_package_id var, allowed_packages'ın id'leriyle filtrele
    allowed_ids = set(str(pkg.id) for pkg in allowed_packages)
    query_embedding = get_embedding(user_input)
    search_result = qdrant_client.search(
        collection_name="gpt_packages",
        query_vector=query_embedding,
        limit=5,  # Birden fazla döndürüp ilk uygun olanı seçmek için
        with_payload=True
    )
    for result in search_result:
        payload = result.payload
        gpt_package_id = payload.get("gpt_package_id")
        if gpt_package_id in allowed_ids:
            score = result.score
            pkg = allowed_packages.filter(id=gpt_package_id).first()
            return pkg, score
    return None, 0.0

def get_embedding(text: str) -> list:
    """
    Given a text string, returns its embedding vector using the sentence transformer model.
    
    Args:
        text (str): Input text to generate embedding for
        
    Returns:
        list: Embedding vector as a list of floats
    """
    return _embedding_model.encode(text).tolist()

def add_to_qdrant(collection_name: str, text: str, payload: dict, context_type: str = "summary") -> bool:
    """
    Add a text and its associated payload to specified Qdrant collection.
    context_type: summary, full, etc.
    """
    try:
        embedding = get_embedding(text)
        payload = dict(payload)
        payload["context_type"] = context_type
        qdrant_client.upsert(
            collection_name=collection_name,
            points=[
                qdrant_models.PointStruct(
                    id=payload.get("id", str(hash(text))), 
                    vector=embedding,
                    payload=payload
                )
            ]
        )
        return True
    except Exception as e:
        print(f"Error adding to Qdrant: {e}")
        return False

def search_qdrant(collection_name: str, text: str = None, filter: dict = None, limit: int = 10) -> list:
    """
    Search specified Qdrant collection using text embedding and/or metadata filters.
    
    Args:
        collection_name (str): Name of the Qdrant collection
        text (str, optional): Text to search by similarity
        filter (dict, optional): Metadata filters to apply
        limit (int): Maximum number of results to return
        
    Returns:
        list: List of search results with scores and payloads
    """
    query_vector = get_embedding(text) if text else None
    
    filter_condition = None
    if filter:
        filter_condition = qdrant_models.Filter(
            must=[
                qdrant_models.FieldCondition(
                    key=k,
                    match=qdrant_models.MatchValue(value=v)
                ) for k, v in filter.items()
            ]
        )
    
    results = qdrant_client.search(
        collection_name=collection_name,
        query_vector=query_vector,
        query_filter=filter_condition,
        limit=limit,
        with_payload=True
    )
    
    return results

def update_qdrant_metadata(collection_name: str, point_id: str, payload: dict) -> bool:
    """
    Update only the metadata/payload for a point in specified Qdrant collection.
    
    Args:
        collection_name (str): Name of the Qdrant collection
        point_id (str): ID of the point to update
        payload (dict): New metadata/payload
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        qdrant_client.set_payload(
            collection_name=collection_name,
            payload=payload,
            points=[point_id]
        )
        return True
    except Exception as e:
        print(f"Error updating Qdrant metadata: {e}")
        return False

def delete_from_qdrant(collection_name: str, point_ids: list) -> bool:
    """
    Delete points from specified Qdrant collection by their IDs.
    
    Args:
        collection_name (str): Name of the Qdrant collection
        point_ids (list): List of point IDs to delete
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        qdrant_client.delete(
            collection_name=collection_name,
            points_selector=qdrant_models.PointIdsList(
                points=point_ids
            )
        )
        return True
    except Exception as e:
        print(f"Error deleting from Qdrant: {e}")
        return False

async def summarize_context(text: str, user_profile=None, gpt_package=None) -> str:
    """
    LLM ile context özetleme. llm_dispatcher.summarize_context fonksiyonunu çağırır.
    """
    # llm_dispatcher'da async fonksiyon, burada sync çağrı için event loop kullanıyoruz
    if hasattr(llm_dispatcher, "summarize_context"):
        if asyncio.get_event_loop().is_running():
            return await llm_dispatcher.summarize_context(text, user_profile, gpt_package)
        else:
            return asyncio.run(llm_dispatcher.summarize_context(text, user_profile, gpt_package))
    # Fallback: ilk 300 karakter
    return text[:300] + ("..." if len(text) > 300 else "")

def search_memory_contexts(user_profile_id: str, query: str, limit: int = 3) -> list:
    """
    Kullanıcıya ait geçmiş context özetlerini semantik olarak arar.
    """
    filter_dict = {"user_profile_id": str(user_profile_id), "context_type": "summary"}
    results = search_qdrant(
        collection_name="conversation_contexts",
        text=query,
        filter=filter_dict,
        limit=limit
    )
    memory_contexts = []
    for r in results:
        payload = r.payload
        memory_contexts.append({
            "summary": payload.get("summary", ""),
            "timestamp": payload.get("timestamp", "")
        })
    return memory_contexts

