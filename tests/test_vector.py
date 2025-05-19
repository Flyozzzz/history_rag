import importlib
import os
import sys
import types
import unittest


# Stub redisvl and numpy modules used by vector
class DummyArray:
    def __init__(self, data, dtype=None):
        self.data = data

    def tobytes(self):
        return b"bytes"


def dummy_asarray(arr, dtype=None):
    return DummyArray(arr, dtype)


class DummyIndex:
    def __init__(self, schema=None, redis_url=None):
        self.created = False
        self.loaded = []

    async def create(self, overwrite=False):
        self.created = True

    async def load(self, docs, id_field=None):
        self.loaded.extend(docs)

    async def query(self, query):
        return [{"message_id": "m1"}, {"message_id": "m2"}]


def dummy_from_dict(d):
    return d


class DummyVectorQuery:
    def __init__(self, *a, **k):
        pass

    def set_filter(self, f):
        self.filter = f


sys.modules["numpy"] = types.SimpleNamespace(asarray=dummy_asarray, float32="f32")

redisvl_pkg = types.SimpleNamespace()
sys.modules["redisvl"] = redisvl_pkg
sys.modules["redisvl.index"] = types.SimpleNamespace(AsyncSearchIndex=DummyIndex)
sys.modules["redisvl.schema"] = types.SimpleNamespace(
    IndexSchema=types.SimpleNamespace(from_dict=dummy_from_dict)
)
sys.modules["redisvl.query"] = types.SimpleNamespace(
    VectorQuery=DummyVectorQuery, filter=types.SimpleNamespace(Tag=lambda *a, **k: None)
)
sys.modules["redisvl.query.filter"] = types.SimpleNamespace(Tag=lambda *a, **k: None)

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
import app.vector as vector

vector = importlib.reload(vector)
vector._idx = None
vector.embedding_dimension = lambda: 2


class VectorTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_upsert_and_search(self):
        await vector.upsert_embedding("u1", "m1", [1.0, 2.0], tags=["t1"])
        ids = await vector.semantic_search("u1", [1.0, 2.0], k=2, tags=["t1"])
        self.assertEqual(ids, ["m1", "m2"])
        self.assertIn(
            {
                "uuid": "u1",
                "message_id": "m1",
                "embedding": b"bytes",
                "tags": "t1",
            },
            vector._idx.loaded,
        )


if __name__ == "__main__":
    unittest.main()
