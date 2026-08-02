from dotenv import load_dotenv
load_dotenv()

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ChatModelSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CHAT_")
    base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    api_key: str = ""
    model_name: str = "qwen-plus"
    temperature: float = 0.7


class EmbeddingModelSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="EMBEDDING_")
    base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    api_key: str = ""
    model_name: str = "text-embedding-v3"
    dimensions: int = 512


class AuthSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AUTH_")
    jwt_secret: str = "change-me-to-a-32byte-secret-key-minimum"
    issuer: str = "argus-rag"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 14
    refresh_cookie_name: str = "ARGUS_DD_RAG_REFRESH_TOKEN"
    refresh_cookie_secure: bool = False


class MinioSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MINIO_")
    endpoint: str = "127.0.0.1:9000"
    access_key: str = "minioadmin"
    secret_key: str = "minioadmin"
    bucket: str = "argus-rag-documents"
    secure: bool = False


class ElasticsearchSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ES_")
    host: str = "127.0.0.1"
    port: int = 9200
    scheme: str = "http"
    index_name: str = "new_rag_document_chunks"


class ChunkingSettings(BaseSettings):
    target_tokens: int = 240
    max_tokens: int = 320
    overlap_tokens: int = 32


class IngestionSettings(BaseSettings):
    chunking: ChunkingSettings = Field(default_factory=ChunkingSettings)
    vector_add_batch_size: int = 9
    max_retries: int = 3
    worker_poll_interval_seconds: int = 2
    worker_id: str = "worker-1"


class DevAdminSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DEV_ADMIN_")
    enabled: bool = True
    email: str = "admin@argus.local"
    username: str = "admin"
    password: str = "Admin@123456"
    display_name: str = "System Admin"


class MineruSettings(BaseSettings):
    """MinerU 云端文档解析 API 配置（https://mineru.net 免费 token）"""
    model_config = SettingsConfigDict(env_prefix="MINERU_")
    token: str = ""
    model: str = "vlm"  # vlm（精度高）/ pipeline（零幻觉）
    base_url: str = "https://mineru.net"
    poll_interval: float = 3.0
    poll_timeout: int = 600
    max_file_size: int = 200 * 1024 * 1024


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/new_rag",
        alias="DATABASE_URL",
    )
    server_host: str = "0.0.0.0"
    server_port: int = 10001
    debug: bool = False
    cors_origins: list[str] = Field(
        default=["http://localhost:5173"],
        alias="CORS_ORIGINS",
    )
    chat: ChatModelSettings = Field(default_factory=ChatModelSettings)
    embedding: EmbeddingModelSettings = Field(default_factory=EmbeddingModelSettings)
    auth: AuthSettings = Field(default_factory=AuthSettings)
    minio: MinioSettings = Field(default_factory=MinioSettings)
    elasticsearch: ElasticsearchSettings = Field(default_factory=ElasticsearchSettings)
    ingestion: IngestionSettings = Field(default_factory=IngestionSettings)
    dev_admin: DevAdminSettings = Field(default_factory=DevAdminSettings)
    mineru: MineruSettings = Field(default_factory=MineruSettings)


settings = Settings()
