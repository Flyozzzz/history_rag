import os
import sys
import unittest

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from app import notify

class DummySettings:
    def __init__(self, service="stub"):
        self.notification_service = service

class NotifyTestCase(unittest.TestCase):
    def test_get_notifier_default_stub(self):
        notify.get_settings = lambda: DummySettings("stub")
        n = notify.get_notifier()
        self.assertIsInstance(n, notify.StubNotifier)

    def test_get_notifier_email(self):
        n = notify.get_notifier("email")
        self.assertIsInstance(n, notify.EmailNotifier)

    def test_get_notifier_push(self):
        n = notify.get_notifier("push")
        self.assertIsInstance(n, notify.PushNotifier)

if __name__ == "__main__":
    unittest.main()
