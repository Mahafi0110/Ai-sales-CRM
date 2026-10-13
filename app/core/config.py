"""Application settings, read from environment variables or the .env file."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "AI Sales & CRM Agent"
    environment: str = "development"
    database_url: str = "postgresql+psycopg2://crm:crm@localhost:5432/crm"
    redis_url: str = "redis://localhost:6379/0"
    secret_key: str = "change-me"
    access_token_expire_minutes: int = 60
    cookie_secure: bool = False  # set true when serving over HTTPS
    # --- AI model (Phase 3). The free Google Gemini tier is the default. ---
    llm_provider: str = "gemini"  # gemini | anthropic | openai
    llm_model: str = "gemini-flash-latest"  # copy a current model name from Google AI Studio if this stops working
    llm_timeout_seconds: int = 45
    # --- Company knowledge / RAG (Phase 5). Keyword search always works; semantic search needs a Gemini key. ---
    knowledge_semantic: bool = True  # set false to use keyword search only
    embedding_model: str = "gemini-embedding-001"
    embedding_dimensions: int = 768  # smaller vectors = less storage; 768 is plenty for this
    knowledge_chunk_size: int = 900  # characters per passage
    knowledge_chunk_overlap: int = 120
    knowledge_max_upload_mb: int = 5
    knowledge_max_chars: int = 300_000  # longest document accepted
    knowledge_min_similarity: float = 0.45  # how close in meaning a passage must be (0-1); tune if results look off
    knowledge_max_passages: int = 10_000  # library size limit; search takes about 0.2 s per 1,000 passages (see README)
    embedding_batch_size: int = 50
    embedding_max_per_reindex: int = 200
    # --- Sending email (Phase 5). "console" only logs the email (nothing is delivered) so you can try everything safely.
    email_backend: str = "console"  # console | smtp
    email_from: str = "crm@localhost"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = True
    email_max_per_hour: int = 20  # per person
    # --- AI assistant (Phase 4): limits that protect the free AI quota ---
    agent_max_steps: int = 6  # most AI "thinking" rounds in one request
    agent_max_tool_calls: int = 12  # most lookups/actions in one request
    agent_max_ai_actions: int = 4  # most AI-powered tools (score a lead, write an email) in one request
    agent_runs_per_hour: int = 20  # per person
    agent_max_proposals: int = 5  # most approval requests the assistant may create in one request
    google_api_key: str = ""
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    currency_symbol: str = "$"  # shown before money amounts on pages
    bcrypt_rounds: int = 12  # password hashing strength; tests lower this to run faster


@lru_cache
def get_settings() -> Settings:
    return Settings()
