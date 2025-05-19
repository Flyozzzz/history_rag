import os
import sys
import types
import unittest
from unittest.mock import AsyncMock, patch

# Reuse stubs from other tests to avoid heavy imports
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
import app.main as mainmod
from app.models import AddRequest, Message, SearchRequest
from app.routes.messages import add_history, search, summarize

app = mainmod.app


class DummySettings:
    def __init__(self):
        self.compression_threshold = 500
        self.compression_algorithm = "gzip"
        self.openai_chat_model = "gpt"
        self.summary_token_threshold = 3000


class UsageTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_add_history_increments_usage(self):
        rds = AsyncMock()
        app.state.redis = rds
        mainmod.settings = DummySettings()
        rds.xlen.return_value = 0
        req = AddRequest(
            uuid="u1", messages=[Message(role="user", type="text", content="hello")]
        )
        with patch(
            "app.history_utils._add_to_stream", AsyncMock(return_value="1")
        ), patch("app.services.messages._embed_and_insert", AsyncMock()), patch(
            "app.services.facts._check_and_store_fact", AsyncMock()
        ), patch(
            "app.services.calendar._check_and_store_calendar_event", AsyncMock()
        ), patch(
            "app.services.company._ensure_company", AsyncMock()
        ), patch(
            "app.main.summarize_if_needed",
            types.SimpleNamespace(delay=lambda *a, **k: None),
        ), patch(
            "app.main.update_facts", types.SimpleNamespace(delay=lambda *a, **k: None)
        ), patch(
            "app.main.increment_messages", AsyncMock()
        ) as inc_msg, patch(
            "app.main.increment_tokens", AsyncMock()
        ) as inc_tok:
            await add_history(req, user=("u1", "c1"))
            inc_msg.assert_awaited_with(rds, "c1", 1)
            inc_tok.assert_awaited_with(rds, "c1", 1)

    async def test_add_history_respects_flags(self):
        rds = AsyncMock()
        app.state.redis = rds
        mainmod.settings = DummySettings()
        rds.xlen.return_value = 0
        req = AddRequest(
            uuid="u1", messages=[Message(role="user", type="text", content="hi")]
        )
        with patch(
            "app.history_utils._add_to_stream", AsyncMock(return_value="1")
        ), patch("app.services.messages._embed_and_insert", AsyncMock()), patch(
            "app.services.facts._check_and_store_fact", AsyncMock()
        ) as chk_fact, patch(
            "app.services.calendar._check_and_store_calendar_event", AsyncMock()
        ) as chk_cal, patch(
            "app.services.company._ensure_company", AsyncMock()
        ), patch(
            "app.services.company._company_feature_enabled",
            AsyncMock(side_effect=[False, False, False]),
        ), patch(
            "app.main.summarize_if_needed", types.SimpleNamespace(delay=AsyncMock())
        ) as sum_task, patch(
            "app.main.update_facts", types.SimpleNamespace(delay=AsyncMock())
        ) as upd_task:
            await add_history(req, user=("u1", "c1"))
            chk_fact.assert_not_awaited()
            chk_cal.assert_not_awaited()
            sum_task.delay.assert_not_called()
            upd_task.delay.assert_not_called()

    async def test_search_increments_usage(self):
        rds = AsyncMock()
        app.state.redis = rds
        mainmod.settings = DummySettings()
        with patch("app.main.embed", AsyncMock(return_value=[])), patch(
            "app.main.semantic_search", AsyncMock(return_value=[])
        ), patch("app.services.company._ensure_company", AsyncMock()), patch(
            "app.main.increment_messages", AsyncMock()
        ) as inc_msg, patch(
            "app.main.increment_tokens", AsyncMock()
        ) as inc_tok:
            req = SearchRequest(uuid="u1", query="hi")
            await search(req, user=("u1", "c1"))
            inc_msg.assert_awaited_with(rds, "c1")
            inc_tok.assert_awaited_with(rds, "c1", 1)

    async def test_summary_increments_usage(self):
        rds = AsyncMock()
        app.state.redis = rds
        mainmod.settings = DummySettings()
        rds.xrange.return_value = []
        dummy_llm = types.SimpleNamespace(
            chat=types.SimpleNamespace(
                completions=types.SimpleNamespace(
                    create=AsyncMock(
                        return_value=types.SimpleNamespace(
                            choices=[
                                types.SimpleNamespace(
                                    message=types.SimpleNamespace(content="sum")
                                )
                            ]
                        )
                    )
                )
            )
        )
        with patch("app.services.llm.llm", dummy_llm), patch(
            "app.services.company._ensure_company", AsyncMock()
        ), patch("app.main.increment_messages", AsyncMock()) as inc_msg, patch(
            "app.main.increment_tokens", AsyncMock()
        ) as inc_tok:
            await summarize(uuid="u1", chat_id=None, user=("u1", "c1"))
            inc_msg.assert_awaited_with(rds, "c1")
            inc_tok.assert_not_awaited()

    async def test_summary_disabled(self):
        rds = AsyncMock()
        app.state.redis = rds
        mainmod.settings = DummySettings()
        with patch("app.services.company._ensure_company", AsyncMock()), patch(
            "app.services.company._company_feature_enabled",
            AsyncMock(return_value=False),
        ):
            with self.assertRaises(mainmod.HTTPException):
                await summarize(uuid="u1", chat_id=None, user=("u1", "c1"))


if __name__ == "__main__":
    unittest.main()
