import os
from pydantic_settings import BaseSettings
from pydantic import Field

class Settings(BaseSettings):
    redis_url: str = Field("redis://redis:6379/0", alias="REDIS_URL")
    redis_index_algorithm: str = Field("flat", alias="REDIS_INDEX_ALGORITHM")
    minio_endpoint: str = Field("localhost:9000", alias="MINIO_ENDPOINT")
    minio_access_key: str = Field("minioadmin", alias="MINIO_ACCESS_KEY")
    minio_secret_key: str = Field("minioadmin", alias="MINIO_SECRET_KEY")
    minio_bucket: str = Field("history", alias="MINIO_BUCKET")
    openai_api_key: str | None = Field(None, alias="OPENAI_API_KEY")
    openai_base_url: str | None = Field("https://api.openai.com/v1", alias="OPENAI_BASE_URL")
    openai_chat_model: str = Field("gpt-3.5-turbo", alias="OPENAI_CHAT_MODEL")
    summary_token_threshold: int = Field(3000, alias="SUMMARY_TOKEN_THRESHOLD")
    hf_embed_model: str = Field("sentence-transformers/all-MiniLM-L6-v2", alias="HF_EMBED_MODEL")
    stt_ws_url: str | None = Field("ws://127.0.0.1:8088/ws", alias="STT_WS_URL")
    encryption_key: str | None = Field(None, alias="ENCRYPTION_KEY")
    admin_key: str | None = Field(None, alias="ADMIN_KEY")
    token_ttl: int = Field(86400, alias="TOKEN_TTL")
    log_level: str = Field("INFO", alias="LOG_LEVEL")
    notification_service: str = Field("stub", alias="NOTIFICATION_SERVICE")
    compression_threshold: int = Field(500, alias="COMPRESSION_THRESHOLD")
    compression_algorithm: str = Field("gzip", alias="COMPRESSION_ALGORITHM")
    cost_per_message: float = Field(0.0, alias="COST_PER_MESSAGE")
    cost_per_token: float = Field(0.0, alias="COST_PER_TOKEN")
    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

def get_settings() -> Settings:
    return Settings()
