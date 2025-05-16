import os
from sentence_transformers import SentenceTransformer
from functools import lru_cache
from app.config import get_settings

settings = get_settings()

@lru_cache
def get_model() -> SentenceTransformer:
    model_name = settings.hf_embed_model
    return SentenceTransformer(model_name, device="cpu")

@lru_cache(maxsize=1024)
def _cached_embed(text: str) -> tuple[float, ...]:
    model = get_model()
    return tuple(model.encode(text, convert_to_numpy=False))

def embed(text: str) -> list[float]:
    return list(_cached_embed(text))

def embedding_dimension() -> int:
    return get_model().get_sentence_embedding_dimension()