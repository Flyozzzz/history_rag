import os
import sys
import types
import unittest
from unittest.mock import AsyncMock, patch

# Reuse stubs from other tests
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
from app.routes.messages import search_by_tag

# Pydantic v1 compatibility
if not hasattr(Message, "model_validate_json"):
    Message.model_validate_json = classmethod(lambda cls, data: cls.parse_raw(data))


class TagSearchTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_search_by_tag(self):
        rds = AsyncMock()
        app.state.redis = rds
        rds.smembers.return_value = {b"1-0"}
        rds.xrange.return_value = [
            ("1-0", {b"data": b'{"role":"user","type":"text","content":"hi"}'})
        ]

        def hget_side(key, mid=None):
            if key == "user:u1:msg_tags":
                return b'["tag"]'
            return b"c1"

        rds.hget.side_effect = hget_side
        with patch("app.services.company._ensure_company", AsyncMock()), patch(
            "app.main.decrypt_text", lambda x: x
        ):
            resp = await search_by_tag(
                uuid="u1", tag="tag", limit=1, chat_id=None, user=("u1", "c1")
            )
            self.assertEqual(len(resp["hits"]), 1)
            self.assertEqual(resp["hits"][0].tags, ["tag"])


if __name__ == "__main__":
    unittest.main()
