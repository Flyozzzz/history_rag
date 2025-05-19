import logging
from .config import get_settings


def setup_logging() -> None:
    settings = get_settings()
    level_name = getattr(settings, "log_level", "INFO")
    if not isinstance(level_name, str):
        level_name = str(level_name)
    level = getattr(logging, level_name.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
