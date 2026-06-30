"""应用配置 - 基于 Pydantic Settings，从环境变量读取"""

from functools import lru_cache
from typing import Any

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ===== 应用配置 =====
    app_name: str = "OmicHub"
    app_env: str = "development"
    app_debug: bool = True
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_secret_key: str = "change-me-in-production"

    # ===== 数据库配置 =====
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "omichub"
    postgres_password: str = "omichub"
    postgres_db: str = "omichub"
    database_url: str = ""

    # ===== Redis 配置 =====
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_password: str = ""
    redis_db: int = 0
    celery_broker_url: str = ""
    celery_result_backend: str = ""

    # ===== JWT 配置 =====
    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # ===== CORS 配置 =====
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    # ===== AI 配置 =====
    llm_provider: str = "kimi"
    kimi_api_key: str = ""
    kimi_base_url: str = "https://api.moonshot.cn/v1"
    kimi_model: str = "moonshot-v1-8k"
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o"

    # ===== 文件存储 =====
    storage_type: str = "local"
    storage_path: str = "/data/omichub"
    upload_dir: str = "uploads"
    results_dir: str = "results"

    # ===== 流程 YAML 配置 =====
    flow_yaml_dir: str = "flows"

    # ===== Snakemake 配置 =====
    snakemake_cores: int = 4
    snakemake_use_conda: bool = True
    # --use-conda 时环境创建目录（须可写，避免只读挂载冲突）
    snakemake_conda_prefix: str = "/data/omichub/.conda_envs"

    # ===== 饼干积分系统 =====
    enable_cookie_system: bool = True
    initial_cookie_balance: float = 100.0
    cookie_sandbox_base_cost: float = 0.5

    # ===== AI Copilot =====
    ai_system_prompt: str = (
        "你是 OmicHub 智能分析助手，专注于多组学（RNA-seq/ATAC-seq 等）数据分析。"
        "回答需简洁专业，代码块标注语言（python/r/bash），数据路径用 /workspace/data 前缀。"
    )
    ai_max_context_messages: int = 20
    ai_temperature: float = 0.7
    ai_default_provider_id: str = ""  # 默认 AI provider 配置 UUID，空则使用环境变量兜底
    ai_provider_key_encryption_key: str = ""  # Fernet 密钥，为空则 API key 明文存储
    ai_provider_config_yaml: str = "data/ai_providers.yaml"  # 外置 AI Provider YAML 配置路径

    # ===== 代码执行沙盒 =====
    sandbox_enabled: bool = True
    sandbox_image: str = "omichub/sandbox-base:latest"
    sandbox_docker_network: str = "omichub_default"
    sandbox_warm_pool_size: int = 2
    sandbox_max_pool_size: int = 10
    sandbox_session_timeout: int = 1800  # 30 分钟无活动回收
    sandbox_exec_timeout: int = 300  # 单次代码执行超时（秒）
    sandbox_data_dir: str = "/data/omichub"
    sandbox_default_cpu: float = 2.0
    sandbox_default_memory: str = "4g"

    # ===== MCP 集成 =====
    mcp_enabled: bool = True
    mcp_default_timeout: int = 30

    @field_validator("database_url", mode="before")
    @classmethod
    def assemble_database_url(cls, v: str, info: Any) -> str:
        if v:
            return v
        values = info.data
        return (
            f"postgresql+asyncpg://{values['postgres_user']}:"
            f"{values['postgres_password']}@{values['postgres_host']}:"
            f"{values['postgres_port']}/{values['postgres_db']}"
        )

    @field_validator("celery_broker_url", mode="before")
    @classmethod
    def assemble_celery_broker(cls, v: str, info: Any) -> str:
        if v:
            return v
        values = info.data
        password_part = f":{values['redis_password']}@" if values["redis_password"] else ""
        return f"redis://{password_part}{values['redis_host']}:{values['redis_port']}/1"

    @field_validator("celery_result_backend", mode="before")
    @classmethod
    def assemble_celery_backend(cls, v: str, info: Any) -> str:
        if v:
            return v
        values = info.data
        password_part = f":{values['redis_password']}@" if values["redis_password"] else ""
        return f"redis://{password_part}{values['redis_host']}:{values['redis_port']}/2"

    @property
    def redis_url(self) -> str:
        password_part = f":{self.redis_password}@" if self.redis_password else ""
        return f"redis://{password_part}{self.redis_host}:{self.redis_port}/{self.redis_db}"

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    """获取配置单例"""
    return Settings()
