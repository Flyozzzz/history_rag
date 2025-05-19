import os
import sys
import types
import unittest
from unittest.mock import AsyncMock, patch

# Stub external dependencies similar to other tests
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
from app.main import app
from app.models import Message
from app.routes.history import get_context

# Provide compatibility for Pydantic v1 used in tests
if not hasattr(Message, "model_validate_json"):
    Message.model_validate_json = classmethod(lambda cls, data: cls.parse_raw(data))


class ContextTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_duplicates_excluded(self):
        rds = AsyncMock()
        app.state.redis = rds
        rds.xrevrange.return_value = [
            ("2-0", {b"data": b'{"role":"user","type":"text","content":"m2"}'}),
            ("1-0", {b"data": b'{"role":"user","type":"text","content":"m1"}'}),
        ]

        async def xrange(key, min=None, max=None):
            if min == "2-0":
                return [
                    ("2-0", {b"data": b'{"role":"user","type":"text","content":"m2"}'})
                ]
            if min == "3-0":
                return [
                    ("3-0", {b"data": b'{"role":"user","type":"text","content":"m3"}'})
                ]
            return []

        rds.xrange.side_effect = xrange
        rds.hget.return_value = None
        with patch("app.routes.history.embed", lambda text: []), patch(
            "app.routes.history.semantic_search", AsyncMock(return_value=["2-0", "3-0"])
        ), patch("app.services.company._ensure_company", AsyncMock()), patch(
            "app.services.facts._aggregate_facts", AsyncMock(return_value=None)
        ), patch(
            "app.routes.history.decrypt_text", lambda x: x
        ):
            resp = await get_context(
                uuid="u1", limit=2, top_k=2, chat_id=None, user=("u1", "c1")
            )
            self.assertEqual([m.content for m in resp["relevant"]], ["m3"])


if __name__ == "__main__":
    unittest.main()
