from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # LLM —— chat / embedding / rerank 都走硅基流动(SiliconFlow)OpenAI 兼容接口
    openai_api_key: str          # 硅基流动 API Key
    openai_base_url: str         # 硅基流动 baseURL:https://api.siliconflow.cn/v1
    chat_model: str              # chat 模型名,如 Qwen/Qwen3.5-4B
    embedding_model: str         # embedding 模型名,如 BAAI/bge-m3
    embedding_dim:int = 1024     # bge-m3 固定 1024 维(不支持 dimensions 参数)
    rerank_model: str = "BAAI/bge-reranker-v2-m3"  # 走 SiliconFlow /v1/rerank

    # Database
    database_url: str
    redis_url: str = "redis://localhost:6380/0"

    # App
    log_level: str = "INFO"
    log_json: bool = False       # True=输出 JSON(生产);False=彩色控制台(本地开发)

settings = Settings() # type: ignore[call-arg]