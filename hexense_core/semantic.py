from hexense_core.models import GptPackage
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.http import models as qdrant_models
from typing import Tuple
import os

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")

_embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
qdrant_client = QdrantClient(QDRANT_URL)

def find_best_gpt_package(user_input: str) -> Tuple[GptPackage, float]:
    query_embedding = get_embedding(user_input)
    search_result = qdrant_client.search(
        collection_name="gpt_packages",
        query_vector=query_embedding,
        limit=1,
        with_payload=True
    )
    if not search_result:
        return None, 0.0
    payload = search_result[0].payload
    gpt_package_id = payload.get("gpt_package_id")
    score = search_result[0].score
    pkg = GptPackage.objects.filter(id=gpt_package_id).first()
    return pkg, score

def get_embedding(text: str) -> list:
    """
    Given a text string, returns its embedding vector using the sentence transformer model.
    
    Args:
        text (str): Input text to generate embedding for
        
    Returns:
        list: Embedding vector as a list of floats
    """
    return _embedding_model.encode(text).tolist()

def add_to_qdrant(collection_name: str, text: str, payload: dict) -> bool:
    """
    Add a text and its associated payload to specified Qdrant collection.
    
    Args:
        collection_name (str): Name of the Qdrant collection
        text (str): Text to generate embedding for
        payload (dict): Metadata/payload to store with the embedding
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        embedding = get_embedding(text)
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

