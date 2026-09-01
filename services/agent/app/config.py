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


settings = Settings()
