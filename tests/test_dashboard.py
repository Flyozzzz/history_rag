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
import app.routes.admin as adminmod
from app.main import app
from app.routes.admin import company_dashboard


class DashboardTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_dashboard_template_context(self):
        rds = AsyncMock()
        app.state.redis = rds
        rds.smembers.return_value = {b"u1", b"u2"}
        with patch(
            "app.usage.get_usage", AsyncMock(return_value={"messages": 5, "tokens": 10})
        ), patch("app.usage.calculate_cost", AsyncMock(return_value=0.7)), patch(
            "app.usage.get_user_usage",
            AsyncMock(side_effect=lambda r, c, u: {"messages": 1, "tokens": 2}),
        ), patch(
            "app.usage.calculate_user_cost",
            AsyncMock(side_effect=lambda r, c, u, s=None: 0.1),
        ), patch.object(
            mainmod,
            "templates",
            types.SimpleNamespace(TemplateResponse=lambda tpl, ctx: (tpl, ctx)),
        ):
            tpl, ctx = await company_dashboard(
                request=types.SimpleNamespace(), company="c1"
            )
            self.assertEqual(tpl, "dashboard.html")
            self.assertEqual(ctx["company"], "c1")
            self.assertEqual(ctx["users"], ["u1", "u2"])
            self.assertEqual(ctx["usage"], {"messages": 5, "tokens": 10})
            self.assertEqual(ctx["cost"], "0.70")
            self.assertIn("user_usage", ctx)
            self.assertEqual(ctx["user_usage"]["u1"]["cost"], "0.10")

    async def test_company_login_sets_cookie(self):
        with patch(
            "app.routes.admin.login_company", AsyncMock(return_value="tok")
        ), patch.object(
            mainmod,
            "templates",
            types.SimpleNamespace(),
        ):
            resp = await adminmod.company_login_post(
                request=types.SimpleNamespace(), name="c1", password="pw"
            )
            self.assertEqual(resp.status_code, 302)
            self.assertEqual(resp.headers["location"], "/company/dashboard")
            self.assertIn("company_token=tok", resp.headers["set-cookie"])


if __name__ == "__main__":
    unittest.main()
