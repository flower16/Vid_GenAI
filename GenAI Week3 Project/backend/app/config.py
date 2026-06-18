"""Central configuration (env-driven). Never hardcode secrets."""
from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Storage
    database_url: str = "sqlite:///./solarbilliq.db"
    upload_dir: str = "./uploads"

    # Pinecone
    pinecone_api_key: str = ""
    pinecone_index: str = "solarbilliq-docs"
    pinecone_cloud: str = "aws"
    pinecone_region: str = "us-east-1"
    default_namespace: str = "oncor_solar_plans"
    utility_area: str = "Oncor"

    # Embeddings / LLM
    embed_model: str = "text-embedding-3-small"   # 1536 dims
    embed_dim: int = 1536
    openai_api_key: str = ""

    # LLM (explanation generation) — Claude Opus 4.8
    anthropic_api_key: str = ""

    # Auth
    jwt_secret: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440  # 24h

    # Multi-agent: external project MCP servers (stdio launch commands).
    # e.g. "python -m finance_rag.mcp.server"  /  "python -m healthcare.mcp.server"
    # Left blank -> that domain reports "not connected".
    finance_mcp_command: str = ""
    healthcare_mcp_command: str = ""

    # Chunking
    chunk_size: int = 512
    chunk_overlap: int = 64

    class Config:
        env_file = ".env"


@lru_cache
def get_settings() -> Settings:
    return Settings()
