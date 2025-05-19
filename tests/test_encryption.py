import unittest
import os
import sys
import types
import base64
import importlib

# Provide Dummy Fernet implementation for tests
class DummyFernet:
    def __init__(self, key: bytes):
        # Mimic cryptography's key validation
        try:
            decoded = base64.urlsafe_b64decode(key)
        except Exception as exc:
            raise ValueError("invalid base64") from exc
        if len(decoded) != 32:
            raise ValueError("Fernet key must be 32 url-safe base64-encoded bytes")
        self.key = key

    def encrypt(self, data: bytes) -> bytes:
        return base64.urlsafe_b64encode(data[::-1] + self.key)

    def decrypt(self, token: bytes) -> bytes:
        decoded = base64.urlsafe_b64decode(token)
        if not decoded.endswith(self.key):
            raise InvalidToken()
        return decoded[:-len(self.key)][::-1]

class InvalidToken(Exception):
    pass

# Stub external modules used by encryption
sys.modules['cryptography'] = types.SimpleNamespace()
sys.modules['cryptography.fernet'] = types.SimpleNamespace(
    Fernet=DummyFernet,
    InvalidToken=InvalidToken,
)

sys.modules.setdefault('pydantic_settings', types.SimpleNamespace(BaseSettings=object))

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from app import encryption
importlib.reload(encryption)

VALID_KEY = base64.urlsafe_b64encode(b'0' * 32).decode()

class DummySettings:
    def __init__(self, key=None):
        self.encryption_key = key
        self.notification_service = 'stub'

class EncryptionTestCase(unittest.TestCase):
    def setUp(self):
        encryption.settings = DummySettings(VALID_KEY)
        encryption._KEY = None

    def test_encrypt_decrypt_round_trip(self):
        text = 'secret'
        token = encryption.encrypt_text(text)
        self.assertNotEqual(token, text)
        self.assertEqual(encryption.decrypt_text(token), text)

    def test_decrypt_invalid_key_returns_input(self):
        text = 'secret'
        token = encryption.encrypt_text(text)
        encryption.settings = DummySettings('invalid')
        encryption._KEY = None
        self.assertEqual(encryption.decrypt_text(token), token)

if __name__ == '__main__':
    unittest.main()
