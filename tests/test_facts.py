import asyncio
import unittest
import os
import sys
from unittest.mock import AsyncMock

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from app.main import _check_and_store_fact, _aggregate_facts, Message

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

if __name__ == '__main__':
    unittest.main()