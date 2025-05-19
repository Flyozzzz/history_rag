import asyncio

from app.embeddings import embed
from app.vector import upsert_embedding


async def _embed_and_insert(uuid: str, message_id: str, text: str) -> None:
    loop = asyncio.get_running_loop()
    emb = await loop.run_in_executor(None, lambda: embed(text))
    await upsert_embedding(uuid, message_id, emb)
