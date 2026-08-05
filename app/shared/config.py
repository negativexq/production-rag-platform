from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ollama_base_url: str = "http://host.docker.internal:11434"
    ollama_model: str = "qwen2.5:3b-instruct"
    ollama_embed_model: str = "nomic-embed-text"

    qdrant_url: str = "http://localhost:6333"

    otel_exporter_otlp_endpoint: str = "http://localhost:4317"


settings = Settings()
