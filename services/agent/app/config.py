from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """从环境变量读取运行时配置。"""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    openai_api_key: SecretStr
    openai_base_url: str
    chat_model: str
    rag_api_base: str = "http://127.0.0.1:8000"
    rag_timeout_seconds: float = 30.0
    agent_database_url: SecretStr | None = None
    database_url: SecretStr | None = None

    @property
    def checkpoint_conninfo(self) -> str:
        # Agent 可独立配置数据库，也兼容项目已有 SQLAlchemy 连接串。
        value = self.agent_database_url or self.database_url
        if value is None:
            raise ValueError("请配置 AGENT_DATABASE_URL 或 DATABASE_URL")
        return value.get_secret_value().replace("postgresql+psycopg://", "postgresql://", 1)


settings = Settings()
