from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # Database (External database from cannamente project)
    database_url: str = "postgresql://myuser:mypassword@host.docker.internal:5432/mydatabase"
    postgres_db: str = "mydatabase"
    postgres_user: str = "myuser"
    postgres_password: str = "mypassword"
    postgres_host: str = "host.docker.internal"
    postgres_port: int = 5432
    
    # OpenAI
    openai_api_key: Optional[str] = None
    
    # FastAPI
    api_v1_str: str = "/api/v1"
    project_name: str = "AI Budtender"
    debug: bool = True
    
    # Vector Search
    embedding_model: str = "text-embedding-ada-002"
    vector_dimension: int = 1536
    search_limit: int = 5
    
    # Mock mode for testing without OpenAI
    mock_mode: bool = False
    
    # Redis Configuration
    redis_url: str = "redis://redis:6379/0"
    redis_host: str = "redis"
    redis_port: int = 6379
    redis_db: int = 0
    
    # Rate Limiting
    rate_limit_requests: int = 100
    rate_limit_period: int = 60
    
    # Logging
    log_level: str = "INFO"
    log_format: str = "json"
    
    # Monitoring & Metrics
    enable_metrics: bool = True
    metrics_port: int = 9090
    
    # Security
    secret_key: str = "your-secret-key-here"
    access_token_expire_minutes: int = 30
    
    # Performance
    cache_ttl: int = 300
    max_connections: int = 100
    
    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings() 