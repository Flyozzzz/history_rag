import os
import numpy as np
from redisvl.index import AsyncSearchIndex
from redisvl.schema import IndexSchema
from redisvl.query import VectorQuery
from redisvl.query.filter import Tag
from app.config import get_settings
from app.embeddings import embedding_dimension

settings = get_settings()

_SCHEMA_DICT = {
    "index": {
        "name": "history_vectors",
        "prefix": "history_vectors",
        "storage_type": "hash",
    },
    "fields": [
        {"name": "uuid", "type": "tag"},
        {"name": "message_id", "type": "tag"},
        {
            "name": "embedding",
            "type": "vector",
            "attrs": {
                "algorithm": "flat",
                "datatype": "float32",
                "dims": embedding_dimension(),
                "distance_metric": "cosine",
            },
        },
    ],
}

_idx: AsyncSearchIndex | None = None

async def _index() -> AsyncSearchIndex:
    global _idx
    if _idx is None:
        schema = IndexSchema.from_dict(_SCHEMA_DICT)
        _idx = AsyncSearchIndex(schema, redis_url=settings.redis_url)
        await _idx.create(overwrite=False)
    return _idx

async def upsert_embedding(uuid: str, message_id: str, embedding: list[float]):
    idx = await _index()
    vec_bytes = np.asarray(embedding, dtype=np.float32).tobytes()
    await idx.load(
        [{"uuid": uuid, "message_id": message_id, "embedding": vec_bytes}],
        id_field="message_id",
    )

async def semantic_search(uuid: str, query_embedding: list[float], k: int = 5) -> list[str]:
    idx = await _index()
    qvec = np.asarray(query_embedding, dtype=np.float32).tobytes()
    query = VectorQuery(
        vector=qvec,
        vector_field_name="embedding",
        num_results=k,
        return_fields=["message_id"],
    )
    query.set_filter(Tag("uuid") == uuid)
    results = await idx.query(query)
    return [r["message_id"] for r in results]
