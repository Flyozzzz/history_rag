from typing import Optional
from cryptography.fernet import Fernet, InvalidToken
from app.config import get_settings

settings = get_settings()

_KEY: Optional[Fernet] = None

def _fernet() -> Optional[Fernet]:
    global _KEY
    if settings.encryption_key is None:
        return None
    if _KEY is None:
        _KEY = Fernet(settings.encryption_key.encode())
    return _KEY

def encrypt_text(text: str) -> str:
    f = _fernet()
    if f is None:
        return text
    return f.encrypt(text.encode()).decode()

def decrypt_text(token: str) -> str:
    f = _fernet()
    if f is None:
        return token
    try:
        return f.decrypt(token.encode()).decode()
    except InvalidToken:
        return token