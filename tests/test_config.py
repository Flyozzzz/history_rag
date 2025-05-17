import os
import sys
import unittest

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from app.config import get_settings

class ConfigTestCase(unittest.TestCase):
    def test_env_loading(self):
        os.environ['OPENAI_API_KEY'] = 'dummy'
        os.environ['OPENAI_BASE_URL'] = 'http://example.com/v1'
        os.environ['ENCRYPTION_KEY'] = 'abc123abc123abc123abc123abc123ab'
        settings = get_settings()
        self.assertEqual(settings.openai_api_key, 'dummy')
        self.assertEqual(settings.openai_base_url, 'http://example.com/v1')
        self.assertEqual(settings.encryption_key, 'abc123abc123abc123abc123abc123ab')

if __name__ == '__main__':
    unittest.main()