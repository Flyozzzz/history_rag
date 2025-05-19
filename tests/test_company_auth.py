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
sys.modules.setdefault(
    "passlib.context",
    types.SimpleNamespace(CryptContext=lambda *a, **k: DummyContext()),
)
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
        self.notification_service = "stub"
        self.cost_per_message = 0.0
        self.cost_per_token = 0.0


app_config.get_settings = lambda: DummySettings()

from app import company_auth

company_auth.settings = app_config.get_settings()


class CompanyAuthTestCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.rds = AsyncMock()
        company_auth.get_redis = AsyncMock(return_value=self.rds)

    async def test_register_sets_token_mapping(self):
        self.rds.exists.return_value = False
        token = await company_auth.register_company("c1", "pass")
        self.rds.hset.assert_awaited_with(
            "company:c1:data",
            mapping={
                "password": "hashed-pass",
                "token": token,
                "idle_timeout": 0,
                "enable_summary": 1,
                "enable_facts": 1,
                "enable_calendar": 1,
            },
        )
        self.rds.set.assert_awaited_with(
            f"company_token:{token}", "c1", ex=company_auth.settings.token_ttl
        )

    async def test_login_updates_token(self):
        self.rds.hgetall.return_value = {b"password": b"hashed-pass", b"token": b"old"}
        token = await company_auth.login_company("c1", "pass")
        self.rds.delete.assert_awaited_with("company_token:old")
        self.rds.hset.assert_awaited_with("company:c1:data", "token", token)
        self.rds.set.assert_awaited_with(
            f"company_token:{token}", "c1", ex=company_auth.settings.token_ttl
        )

    async def test_get_current_company(self):
        self.rds.get.return_value = "c1"
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="tkn")
        name = await company_auth.get_current_company(credentials=creds)
        self.assertEqual(name, "c1")

    async def test_get_current_company_from_cookie(self):
        self.rds.get.return_value = "c1"
        name = await company_auth.get_current_company(
            credentials=None, token_cookie="tkn"
        )
        self.assertEqual(name, "c1")

    async def test_invalid_token(self):
        self.rds.get.return_value = None
        with self.assertRaises(company_auth.HTTPException):
            creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="bad")
            await company_auth.get_current_company(credentials=creds)

    async def test_rotate_key_updates_and_invalidates_old(self):
        self.rds.hgetall.return_value = {b"password": b"hashed-pass", b"token": b"old"}
        new_token = await company_auth.rotate_company_key("c1")
        self.rds.delete.assert_awaited_with("company_token:old")
        self.rds.hset.assert_awaited_with("company:c1:data", "token", new_token)
        self.rds.set.assert_awaited_with(
            f"company_token:{new_token}", "c1", ex=company_auth.settings.token_ttl
        )

    async def test_token_validation_after_rotation(self):
        self.rds.hgetall.return_value = {b"password": b"hashed-pass", b"token": b"old"}
        new_token = await company_auth.rotate_company_key("c1")

        def getter(key):
            if key == f"company_token:{new_token}":
                return "c1"
            return None

        self.rds.get.side_effect = getter
        with self.assertRaises(company_auth.HTTPException):
            old_creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="old")
            await company_auth.get_current_company(credentials=old_creds)
        new_creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=new_token)
        name = await company_auth.get_current_company(credentials=new_creds)
        self.assertEqual(name, "c1")

    async def test_update_company_flags(self):
        self.rds.hgetall.return_value = {
            b"enable_summary": b"1",
            b"enable_facts": b"1",
            b"enable_calendar": b"1",
        }
        res = await company_auth.update_company_flags(
            "c1", company_auth.CompanyFlagsUpdate(enable_summary=False)
        )
        self.rds.hset.assert_awaited_with(
            "company:c1:data", mapping={"enable_summary": 0}
        )
        self.assertFalse(res["enable_summary"])


if __name__ == "__main__":
    unittest.main()
