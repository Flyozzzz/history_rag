import os
import sys
import types
import unittest
import importlib

# Stub websockets module to avoid network operations
class DummyWS:
    def __init__(self):
        self.sent = []
    async def send(self, data):
        self.sent.append(data)
    async def recv(self):
        return "result"

class DummyConn:
    def __init__(self):
        self.ws = DummyWS()
    async def __aenter__(self):
        return self.ws
    async def __aexit__(self, exc_type, exc, tb):
        pass

types_ws = types.SimpleNamespace(connect=lambda *a, **k: DummyConn())
sys.modules["websockets"] = types_ws

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
import app.transcriber as trans
importlib.reload(trans)  # ensure our stubs are used

class TranscriberTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_clean_transcription(self):
        txt = "hello \u0421\u0443\u0431\u0442\u0438\u0442\u0440\u044b \u0441\u0434\u0435\u043b\u0430\u043b DimaTorzok"
        cleaned = trans.AudioTranscriber._clean_transcription(txt)
        self.assertNotIn("DimaTorzok", cleaned)

    async def test_transcribe_audio(self):
        t = trans.AudioTranscriber("ws://test")
        res = await t.transcribe_audio("data", "prompt")
        self.assertEqual(res, "result")

if __name__ == "__main__":
    unittest.main()
