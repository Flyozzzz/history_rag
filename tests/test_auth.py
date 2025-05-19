import os
import sys
import types
import unittest
from unittest.mock import AsyncMock
from fastapi.security import HTTPAuthorizationCredentials

# Stub dependencies
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

class DummyContext:
    def hash(self, password):
        return f"hashed-{password}"

    def verify(self, password, hashed):
        return hashed == f"hashed-{password}"

sys.modules.setdefault("passlib", types.SimpleNamespace())
sys.modules.setdefault("passlib.context", types.SimpleNamespace(CryptContext=lambda *a, **k: DummyContext()))
sys.modules.setdefault("pydantic_settings", types.SimpleNamespace(BaseSettings=object))

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from app import config as app_config

class DummySettings:
    def __init__(self):
        self.redis_url = "redis://"
        self.redis_index_algorithm = "flat"
        self.minio_endpoint = ""
        self.minio_access_key = ""
        self.minio_secret_key = ""
        self.minio_bucket = "history"
        self.openai_api_key = None
        self.openai_base_url = None
        self.summary_token_threshold = 3000
        self.hf_embed_model = "dummy"
        self.stt_ws_url = None
        self.encryption_key = None
        self.admin_key = None
        self.token_ttl = 100
        self.notification_service = 'stub'
        self.cost_per_message = 0.0
        self.cost_per_token = 0.0

app_config.get_settings = lambda: DummySettings()

from app import auth

auth.settings = app_config.get_settings()

class AuthTestCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.rds = AsyncMock()
        auth.get_redis = AsyncMock(return_value=self.rds)

    async def test_register_sets_token_mapping(self):
        self.rds.exists.return_value = False
        token = await auth.register_user("u1", "pass", "c1")
        self.rds.hset.assert_awaited_with(
            "user:u1:data", mapping={"password": "hashed-pass", "token": token, "company_id": "c1"}
        )
        self.rds.sadd.assert_awaited_with("company:c1:users", "u1")
        self.rds.set.assert_awaited_with(
            f"token:{token}", "u1:c1", ex=auth.settings.token_ttl
        )

    async def test_login_updates_token(self):
        self.rds.hgetall.return_value = {
            b"password": b"hashed-pass",
            b"token": b"old",
            b"company_id": b"c1",
        }
        token = await auth.login_user("u1", "pass")
        self.rds.delete.assert_awaited_with("token:old")
        self.rds.hset.assert_awaited_with("user:u1:data", "token", token)
        self.rds.set.assert_awaited_with(
            f"token:{token}", "u1:c1", ex=auth.settings.token_ttl
        )

    async def test_get_current_user(self):
        self.rds.get.return_value = "u1:c1"
        self.rds.hget.return_value = b"c1"
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="tkn")
        user = await auth.get_current_user(credentials=creds)
        self.assertEqual(user, ("u1", "c1"))

    async def test_invalid_token(self):
        self.rds.get.return_value = None
        with self.assertRaises(auth.HTTPException):
            creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="bad")
            await auth.get_current_user(credentials=creds)


if __name__ == "__main__":
    unittest.main()
