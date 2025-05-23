from hexense_core.models import GptPackage
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.http import models as qdrant_models
from typing import Tuple
import os

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_COLLECTION = "gpt_packages"

_embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
qdrant_client = QdrantClient(QDRANT_URL)

def find_best_gpt_package(user_input: str) -> Tuple[GptPackage, float]:
    query_embedding = _embedding_model.encode(user_input).tolist()
    search_result = qdrant_client.search(
        collection_name=QDRANT_COLLECTION,
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
