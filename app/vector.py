import logging

import numpy as np
from redisvl.index import AsyncSearchIndex
from redisvl.query import VectorQuery
from redisvl.query.filter import Tag
from redisvl.schema import IndexSchema

from app.config import get_settings
from app.embeddings import embedding_dimension

logger = logging.getLogger(__name__)

settings = get_settings()

ALGO = settings.redis_index_algorithm
_SCHEMA_DICT = {
    "index": {
        "name": "history_vectors",
        "prefix": "history_vectors",
        "storage_type": "hash",
    },
    "fields": [
        {"name": "uuid", "type": "tag"},
        {"name": "message_id", "type": "tag"},
        {"name": "tags", "type": "tag"},
        {
            "name": "embedding",
            "type": "vector",
            "attrs": {
                "algorithm": ALGO,
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
        logger.info("Creating vector index")
        schema = IndexSchema.from_dict(_SCHEMA_DICT)
        _idx = AsyncSearchIndex(schema, redis_url=settings.redis_url)
        await _idx.create(overwrite=False)
    return _idx


async def upsert_embedding(
    uuid: str,
    message_id: str,
    embedding: list[float],
    tags: list[str] | None = None,
) -> None:
    logger.debug("Upserting embedding for %s", message_id)
    idx = await _index()
    vec_bytes = np.asarray(embedding, dtype=np.float32).tobytes()
    doc = {"uuid": uuid, "message_id": message_id, "embedding": vec_bytes}
    if tags:
        doc["tags"] = ",".join(tags)
    await idx.load([doc], id_field="message_id")


async def semantic_search(
    uuid: str,
    query_embedding: list[float],
    k: int = 5,
    tags: list[str] | None = None,
) -> list[str]:
    logger.debug("Semantic search for %s", uuid)
    idx = await _index()
    qvec = np.asarray(query_embedding, dtype=np.float32).tobytes()
    query = VectorQuery(
        vector=qvec,
        vector_field_name="embedding",
        num_results=k,
        return_fields=["message_id"],
    )
    flt = Tag("uuid") == uuid
    if tags:
        flt &= Tag("tags").any(tags)
    query.set_filter(flt)
    results = await idx.query(query)
    return [r["message_id"] for r in results]
