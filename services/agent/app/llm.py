from functools import lru_cache

from langchain_openai import ChatOpenAI

from app.config import settings


@lru_cache
def get_chat_client(model: str | None = None) -> ChatOpenAI:
    """按模型复用客户端，并集中管理模型服务配置。"""

    return ChatOpenAI(
        model=model or settings.chat_model,
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
    )
