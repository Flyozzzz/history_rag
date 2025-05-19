import os
import sys
import unittest
import types

sys.modules.setdefault('pydantic_settings', types.SimpleNamespace(BaseSettings=object))
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from app import config as app_config

class DummySettings:
    def __init__(self):
        self.redis_url = os.environ.get('REDIS_URL', 'redis://localhost/0')
        self.redis_index_algorithm = 'flat'
        self.minio_endpoint = ''
        self.minio_access_key = ''
        self.minio_secret_key = ''
        self.minio_bucket = 'history'
        self.openai_api_key = os.environ.get('OPENAI_API_KEY')
        self.openai_base_url = os.environ.get('OPENAI_BASE_URL')
        self.summary_token_threshold = 3000
        self.hf_embed_model = 'dummy'
        self.stt_ws_url = None
        self.encryption_key = os.environ.get('ENCRYPTION_KEY')
        self.admin_key = None
        self.token_ttl = 86400
        self.notification_service = os.environ.get('NOTIFICATION_SERVICE', 'stub')
        self.cost_per_message = 0.0
        self.cost_per_token = 0.0

app_config.get_settings = lambda: DummySettings()

class ConfigTestCase(unittest.TestCase):
    def test_env_loading(self):
        os.environ['OPENAI_API_KEY'] = 'dummy'
        os.environ['OPENAI_BASE_URL'] = 'http://example.com/v1'
        os.environ['ENCRYPTION_KEY'] = 'abc123abc123abc123abc123abc123ab'
        os.environ['NOTIFICATION_SERVICE'] = 'email'
        settings = app_config.get_settings()
        self.assertEqual(settings.openai_api_key, 'dummy')
        self.assertEqual(settings.openai_base_url, 'http://example.com/v1')
        self.assertEqual(settings.encryption_key, 'abc123abc123abc123abc123abc123ab')
        self.assertEqual(settings.notification_service, 'email')

    def test_default_encryption_key_is_none(self):
        if 'ENCRYPTION_KEY' in os.environ:
            del os.environ['ENCRYPTION_KEY']
        if 'NOTIFICATION_SERVICE' in os.environ:
            del os.environ['NOTIFICATION_SERVICE']
        settings = app_config.get_settings()
        self.assertIsNone(settings.encryption_key)
        self.assertEqual(settings.notification_service, 'stub')

if __name__ == '__main__':
    unittest.main()