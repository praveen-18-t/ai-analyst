from urllib.parse import quote_plus

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: str = "dev"
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:3000"

    # App database (Postgres in docker/AWS, SQLite fallback for tests)
    database_url: str = "sqlite:///./data/app.db"
    db_host: str = ""
    db_port: int = 5432
    db_name: str = "analyst"
    db_user: str = "analyst"
    db_password: str = ""

    # Storage / data lake
    data_dir: str = "./data"
    storage: str = "local"  # local | s3
    s3_bucket: str = ""
    aws_region: str = "us-east-1"
    max_upload_mb: int = 200

    # Query engine
    query_engine: str = "duckdb"  # duckdb | athena
    athena_workgroup: str = "ai-analyst"
    athena_output: str = ""  # s3://bucket/prefix/
    glue_database_prefix: str = "ai_analyst"
    max_rows: int = 10000
    query_timeout_s: int = 30

    # Auth
    auth_mode: str = "dev"  # dev | cognito
    cognito_user_pool_id: str = ""
    cognito_client_id: str = ""

    # LLM
    llm_provider: str = "anthropic"  # anthropic | bedrock
    anthropic_api_key: str = ""
    llm_model: str = "claude-sonnet-5-5"
    # Verify the exact model / inference-profile id available in your Bedrock account.
    bedrock_model_id: str = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
    max_sql_retries: int = 3
    price_in_per_mtok: float = 3.0
    price_out_per_mtok: float = 15.0

    # RAG
    embeddings_provider: str = "hash"  # hash | bedrock
    bedrock_embed_model: str = "amazon.titan-embed-text-v2:0"

    # Limits / security
    max_questions_per_day: int = 500
    allow_private_hosts: bool = True  # set false in prod (SSRF guard for DB/API imports)

    @property
    def effective_database_url(self) -> str:
        if self.db_host and self.db_password:
            return (
                f"postgresql+psycopg://{self.db_user}:{quote_plus(self.db_password)}"
                f"@{self.db_host}:{self.db_port}/{self.db_name}"
            )
        return self.database_url


settings = Settings()
