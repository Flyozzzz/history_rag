import asyncio
import json
import os
import sys
import types
import unittest
from unittest.mock import AsyncMock, patch

# Stub external dependencies for tests
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
from datetime import datetime

from app.main import app
from app.models import Message
from app.routes.calendar import delete_calendar, update_calendar
from app.services.calendar import (
    _add_event,
    _batch_check_calendar_events,
    _check_and_store_calendar_event,
    _delete_event,
    _list_events,
    _update_event,
)
from worker import tasks

tasks.send_notification.apply_async = lambda *a, **k: None
from app.models import CalendarDeleteRequest, CalendarUpdateRequest


class DummySettings:
    def __init__(self):
        self.openai_chat_model = "gpt"


class CalendarTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_event_added(self):
        rds = AsyncMock()
        msg = Message(role="user", content="напомни завтра в 18:00 о встрече")
        await _check_and_store_calendar_event(rds, "u1", msg, tz="Europe/Moscow")
        rds.zadd.assert_awaited()
        args, kwargs = rds.zadd.await_args
        stored = list(args[1].keys())[0]
        data = json.loads(stored)
        self.assertEqual(data["tz"], "Europe/Moscow")

    async def test_event_added_via_llm(self):
        rds = AsyncMock()
        dummy_llm = types.SimpleNamespace(
            chat=types.SimpleNamespace(
                completions=types.SimpleNamespace(
                    create=AsyncMock(
                        return_value=types.SimpleNamespace(
                            choices=[
                                types.SimpleNamespace(
                                    message=types.SimpleNamespace(
                                        tool_calls=[
                                            types.SimpleNamespace(
                                                function=types.SimpleNamespace(
                                                    name="add_event",
                                                    arguments=json.dumps(
                                                        {
                                                            "when": "2025-01-01T12:00:00",
                                                            "text": "meet",
                                                        }
                                                    ),
                                                )
                                            )
                                        ]
                                    )
                                )
                            ]
                        )
                    )
                )
            )
        )
        with patch("app.services.llm.llm", dummy_llm), patch(
            "app.main.settings", DummySettings()
        ):
            msg = Message(role="user", content="поставь напоминание")
            await _check_and_store_calendar_event(rds, "u1", msg)
            rds.zadd.assert_awaited()

    async def test_ignore_non_calendar_message(self):
        rds = AsyncMock()
        dummy_llm = types.SimpleNamespace(
            chat=types.SimpleNamespace(
                completions=types.SimpleNamespace(create=AsyncMock())
            )
        )
        with patch("app.services.llm.llm", dummy_llm), patch(
            "app.main.settings", DummySettings()
        ):
            msg = Message(role="user", content="просто текст")
            await _check_and_store_calendar_event(rds, "u1", msg)
            dummy_llm.chat.completions.create.assert_not_awaited()
            rds.zadd.assert_not_awaited()

    async def test_event_deleted_via_llm(self):
        rds = AsyncMock()
        dummy_llm = types.SimpleNamespace(
            chat=types.SimpleNamespace(
                completions=types.SimpleNamespace(
                    create=AsyncMock(
                        return_value=types.SimpleNamespace(
                            choices=[
                                types.SimpleNamespace(
                                    message=types.SimpleNamespace(
                                        tool_calls=[
                                            types.SimpleNamespace(
                                                function=types.SimpleNamespace(
                                                    name="delete_event",
                                                    arguments=json.dumps({"index": 0}),
                                                )
                                            )
                                        ]
                                    )
                                )
                            ]
                        )
                    )
                )
            )
        )
        with patch("app.services.llm.llm", dummy_llm), patch(
            "app.main.settings", DummySettings()
        ):
            msg = Message(role="user", content="удали напоминание 0")
            await _check_and_store_calendar_event(rds, "u1", msg)
            rds.zremrangebyrank.assert_awaited_with("user:u1:calendar", 0, 0)

    async def test_event_updated_via_llm(self):
        rds = AsyncMock()
        dummy_llm = types.SimpleNamespace(
            chat=types.SimpleNamespace(
                completions=types.SimpleNamespace(
                    create=AsyncMock(
                        return_value=types.SimpleNamespace(
                            choices=[
                                types.SimpleNamespace(
                                    message=types.SimpleNamespace(
                                        tool_calls=[
                                            types.SimpleNamespace(
                                                function=types.SimpleNamespace(
                                                    name="update_event",
                                                    arguments=json.dumps(
                                                        {"index": 1, "text": "new"}
                                                    ),
                                                )
                                            )
                                        ]
                                    )
                                )
                            ]
                        )
                    )
                )
            )
        )
        rds.zrange.return_value = [(json.dumps({"text": "old"}), 1000)]
        with patch("app.services.llm.llm", dummy_llm), patch(
            "app.main.settings", DummySettings()
        ):
            msg = Message(role="user", content="измени напоминание")
            await _check_and_store_calendar_event(rds, "u1", msg)
            rds.zremrangebyrank.assert_awaited_with("user:u1:calendar", 1, 1)

    async def test_event_list_via_llm(self):
        rds = AsyncMock()
        dummy_llm = types.SimpleNamespace(
            chat=types.SimpleNamespace(
                completions=types.SimpleNamespace(
                    create=AsyncMock(
                        return_value=types.SimpleNamespace(
                            choices=[
                                types.SimpleNamespace(
                                    message=types.SimpleNamespace(
                                        tool_calls=[
                                            types.SimpleNamespace(
                                                function=types.SimpleNamespace(
                                                    name="list_events",
                                                    arguments=json.dumps({}),
                                                )
                                            )
                                        ]
                                    )
                                )
                            ]
                        )
                    )
                )
            )
        )
        rds.zrange.return_value = []
        with patch("app.services.llm.llm", dummy_llm), patch(
            "app.main.settings", DummySettings()
        ):
            msg = Message(role="user", content="покажи напоминания")
            await _check_and_store_calendar_event(rds, "u1", msg)
            rds.zrange.assert_awaited()

    async def test_update_calendar(self):
        rds = AsyncMock()
        app.state.redis = rds
        rds.zrange.return_value = [(json.dumps({"text": "old"}), 1000)]
        rds.hget.return_value = b"c1"
        req = CalendarUpdateRequest(uuid="u1", text="new", when=datetime(2025, 1, 1))
        await update_calendar(0, req, user=("u1", "c1"))
        rds.zremrangebyrank.assert_awaited_with("user:u1:calendar", 0, 0)
        rds.zadd.assert_awaited()

    async def test_delete_calendar(self):
        rds = AsyncMock()
        app.state.redis = rds
        req = CalendarDeleteRequest(uuid="u1")
        rds.hget.return_value = b"c1"
        await delete_calendar(1, req, user=("u1", "c1"))
        rds.zremrangebyrank.assert_awaited_with("user:u1:calendar", 1, 1)

    async def test_calendar_disabled(self):
        rds = AsyncMock()
        app.state.redis = rds
        req = CalendarDeleteRequest(uuid="u1")
        rds.hget.return_value = b"c1"
        with patch(
            "app.services.company._company_feature_enabled",
            AsyncMock(return_value=False),
        ):
            with self.assertRaises(app.main.HTTPException):
                await delete_calendar(1, req, user=("u1", "c1"))

    async def test_list_add_update_delete(self):
        rds = AsyncMock()
        app.state.redis = rds
        rds.zrange.return_value = []
        events = await _list_events(rds, "u1")
        self.assertEqual(events, [])

        await _add_event(rds, "u1", "2025-01-01T10:00:00", "test")
        rds.zadd.assert_awaited()

        rds.zrange.return_value = [
            (json.dumps({"text": "test", "tz": "UTC"}), 1735725600)
        ]
        events = await _list_events(rds, "u1")
        self.assertEqual(events[0]["index"], 0)

        await _update_event(rds, "u1", 0, text="new")
        rds.zremrangebyrank.assert_awaited_with("user:u1:calendar", 0, 0)
        rds.zadd.assert_awaited()

        await _delete_event(rds, "u1", 0)
        rds.zremrangebyrank.assert_awaited_with("user:u1:calendar", 0, 0)

    async def test_batch_reminder_detection(self):
        rds = AsyncMock()
        msg1 = Message(role="user", content="напомни завтра")
        msg2 = Message(role="user", content="в 18:00 о встрече")
        await _batch_check_calendar_events(rds, "u1", [msg1, msg2])
        rds.zadd.assert_awaited()


if __name__ == "__main__":
    unittest.main()
