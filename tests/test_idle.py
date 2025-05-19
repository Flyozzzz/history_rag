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
from worker import tasks as worker_tasks


class IdleProcessingTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_idle_user_triggers_processing(self):
        rds = AsyncMock()
        worker_tasks.redis.Redis = lambda *a, **k: rds
        rds.keys.return_value = [b"user:u1:data"]

        now = 1000

        async def hget_side_effect(key, field):
            if key == "user:u1:data" and field == "company_id":
                return b"c1"
            if key == "company:c1:data" and field == "idle_timeout":
                return b"10"
            return None

        rds.hget.side_effect = hget_side_effect
        rds.get.return_value = str(now - 20)
        rds.xrevrange.return_value = [
            ("1-0", {b"data": b'{"role":"user","content":"hello"}'})
        ]

        with patch.object(
            worker_tasks,
            "summarize_if_needed",
            types.SimpleNamespace(delay=AsyncMock()),
        ) as sum_task, patch.object(
            worker_tasks,
            "update_facts",
            types.SimpleNamespace(delay=AsyncMock()),
        ) as upd_task, patch(
            "app.services.calendar._check_and_store_calendar_event",
            AsyncMock(),
        ) as chk, patch(
            "app.encryption.decrypt_text", lambda x: x
        ):
            await worker_tasks._async_process_idle_users()
            sum_task.delay.assert_called_with(
                "u1", worker_tasks.settings.summary_token_threshold
            )
            upd_task.delay.assert_called_with("u1")
            chk.assert_awaited()


if __name__ == "__main__":
    unittest.main()
