from typing import Optional
from cryptography.fernet import Fernet, InvalidToken
from app.config import get_settings
import logging

logger = logging.getLogger(__name__)

settings = get_settings()

_KEY: Optional[Fernet] = None

def _fernet() -> Optional[Fernet]:
    global _KEY
    if settings.encryption_key is None:
        return None
    if _KEY is None:
        logger.debug("Initializing Fernet")
        try:
            _KEY = Fernet(settings.encryption_key.encode())
        except (ValueError, TypeError) as exc:
            logger.error("Invalid encryption key: %s", exc)
            return None
    return _KEY

def encrypt_text(text: str) -> str:
    f = _fernet()
    if f is None:
        return text
    logger.debug("Encrypting text")
    return f.encrypt(text.encode()).decode()

def decrypt_text(token: str) -> str:
    f = _fernet()
    if f is None:
        return token
    try:
        logger.debug("Decrypting text")
        return f.decrypt(token.encode()).decode()
    except InvalidToken:
        logger.warning("Invalid encryption token")
        return token
