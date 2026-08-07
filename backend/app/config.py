from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "TerraRAG"
    environment: str = "development"
    ollama_url: str = "http://127.0.0.1:11434"
    qdrant_url: str = "http://qdrant:6333"
    llm_model: str = "gemma4:latest"
    embedding_model: str = "qwen3-embedding:0.6b"
    sqlite_path: Path = Path("./data/terrarag.sqlite3")
    repository_root: Path = Path(".")
    debug_log_chunks: bool = Field(default=False)


@lru_cache
def get_settings() -> Settings:
    return Settings()
