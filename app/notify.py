import logging
from .config import get_settings

logger = logging.getLogger(__name__)

class Notifier:
    async def send(self, uuid: str, text: str) -> None:  # pragma: no cover - interface
        raise NotImplementedError

class StubNotifier(Notifier):
    async def send(self, uuid: str, text: str) -> None:
        logger.info("Stub notification for %s: %s", uuid, text)

# Placeholder classes for future implementation
class EmailNotifier(StubNotifier):
    pass

class PushNotifier(StubNotifier):
    pass


def get_notifier(name: str | None = None) -> Notifier:
    if name is None:
        name = get_settings().notification_service
    if name == "email":
        return EmailNotifier()
    if name == "push":
        return PushNotifier()
    return StubNotifier()
