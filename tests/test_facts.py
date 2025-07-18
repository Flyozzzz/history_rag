import asyncio
import os
import sys
import types
import unittest
from unittest.mock import AsyncMock

sys.modules.setdefault(
    "redis",
    types.SimpleNamespace(
        asyncio=types.SimpleNamespace(
            from_url=lambda *a, **k: None,
            ConnectionPool=types.SimpleNamespace(from_url=lambda *a, **k: None),
            Redis=lambda *a, **k: types.SimpleNamespace(),
        ),
        ConnectionPool=types.SimpleNamespace(from_url=lambda *a, **k: None),
        Redis=lambda *a, **k: types.SimpleNamespace(),
    ),
)
sys.modules.setdefault(
    "openai", types.SimpleNamespace(AsyncOpenAI=lambda *a, **k: None)
)
sys.modules.setdefault(
    "tiktoken", types.SimpleNamespace(get_encoding=lambda name: lambda x: [])
)


class DummyModel:
    def encode(self, *a, **k):
        return []

    def get_sentence_embedding_dimension(self):
        return 0


sys.modules.setdefault(
    "sentence_transformers",
    types.SimpleNamespace(SentenceTransformer=lambda *a, **k: DummyModel()),
)
redisvl_pkg = types.SimpleNamespace()
redisvl_index = types.SimpleNamespace(AsyncSearchIndex=object)
redisvl_schema = types.SimpleNamespace(IndexSchema=object)
redisvl_filter = types.SimpleNamespace(Tag=object)
redisvl_query = types.SimpleNamespace(VectorQuery=object, filter=redisvl_filter)
sys.modules.setdefault("redisvl", redisvl_pkg)
sys.modules.setdefault("redisvl.index", redisvl_index)
sys.modules.setdefault("redisvl.schema", redisvl_schema)
sys.modules.setdefault("redisvl.query", redisvl_query)
sys.modules.setdefault("redisvl.query.filter", redisvl_filter)
sys.modules.setdefault("pydantic_settings", types.SimpleNamespace(BaseSettings=object))
sys.modules.setdefault("aioboto3", types.SimpleNamespace(Session=lambda *a, **k: None))
sys.modules.setdefault("numpy", types.SimpleNamespace(array=lambda *a, **k: None))
sys.modules.setdefault("websockets", types.SimpleNamespace())
passlib_pkg = types.SimpleNamespace()
passlib_context = types.SimpleNamespace(CryptContext=lambda *a, **k: None)
sys.modules.setdefault("passlib", passlib_pkg)
sys.modules.setdefault("passlib.context", passlib_context)
crypto_pkg = types.SimpleNamespace()
fernet_mod = types.SimpleNamespace(Fernet=lambda *a, **k: None, InvalidToken=Exception)
sys.modules.setdefault("cryptography", crypto_pkg)
sys.modules.setdefault("cryptography.fernet", fernet_mod)


class DummyCelery:
    def __init__(self, *a, **k):
        self.conf = types.SimpleNamespace()

    def task(self, func=None, *a, **k):
        if func:
            return func

        def wrapper(f):
            return f

        return wrapper


sys.modules.setdefault("celery", types.SimpleNamespace(Celery=DummyCelery))
sys.modules.setdefault(
    "celery.schedules", types.SimpleNamespace(crontab=lambda *a, **k: None)
)

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from app.main import Message
from app.models import DeleteFactRequest
from app.routes.facts import delete_fact, list_facts
from app.services.facts import (
    _aggregate_facts,
    _check_and_store_fact,
    _delete_fact,
    _list_facts,
)


class FactsTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_check_and_store_fact_adds(self):
        rds = AsyncMock()
        msg = Message(role="user", content="remember: test")
        await _check_and_store_fact(rds, "u1", msg)
        rds.sadd.assert_awaited_with("user:u1:facts", "test")

    async def test_aggregate_facts_none(self):
        rds = AsyncMock()
        rds.smembers.return_value = set()
        res = await _aggregate_facts(rds, "u1")
        self.assertIsNone(res)

    async def test_aggregate_facts_message(self):
        rds = AsyncMock()
        rds.smembers.return_value = {b"one", b"two"}
        res = await _aggregate_facts(rds, "u1")
        self.assertEqual(res.content, "one; two")

    async def test_list_facts_route(self):
        rds = AsyncMock()
        rds.smembers.return_value = {b"a", b"b"}
        from app.main import app

        app.state.redis = rds
        rds.hget.return_value = b"c1"
        resp = await list_facts(uuid="u1", user=("u1", "c1"))
        self.assertEqual(resp["facts"], ["a", "b"])
        rds.smembers.assert_awaited_with("user:u1:facts")

    async def test_delete_fact_route(self):
        rds = AsyncMock()
        rds.srem.return_value = 1
        from app.main import app

        app.state.redis = rds
        req = DeleteFactRequest(uuid="u1", fact="a")
        rds.hget.return_value = b"c1"
        resp = await delete_fact(req, user=("u1", "c1"))
        self.assertEqual(resp["removed"], 1)
        rds.srem.assert_awaited_with("user:u1:facts", "a")

    async def test_update_facts_uses_last_id(self):
        from worker import tasks as worker_tasks

        rds = AsyncMock()
        worker_tasks.redis.Redis = lambda *a, **k: rds
        rds.get.return_value = b"1-0"
        rds.xrange.return_value = [
            ("2-0", {b"data": b'{"role":"user","content":"remember: a"}'}),
            ("3-0", {b"data": b'{"role":"user","content":"remember: b"}'}),
        ]
        await worker_tasks._async_update_facts("u1")
        rds.xrange.assert_awaited_with("user:u1:history", min="(1-0", max="+")
        rds.sadd.assert_awaited_with("user:u1:facts", "a", "b")
        rds.set.assert_awaited_with("facts:last:u1", "3-0")


if __name__ == "__main__":
    unittest.main()
