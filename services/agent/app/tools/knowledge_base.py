import httpx
from langchain_core.tools import tool

from app.config import settings
from app.schemas import KnowledgeQueryResponse


@tool
async def search_knowledge_base(query: str) -> str:
    """查询内部技术知识库，返回可用于回答问题的依据。"""

    async with httpx.AsyncClient(
        base_url=settings.rag_api_base.rstrip("/"),
        timeout=settings.rag_timeout_seconds,
    ) as client:
        response = await client.post(
            "/query",
            json={"question": query, "top_k": 3},
        )
        response.raise_for_status()

    payload = KnowledgeQueryResponse.model_validate(response.json())
    if not payload.sources:
        return "知识库中没有检索到相关内容。"

    return "\n\n".join(
        f"文档名：{source.document_filename} / 内容：{source.content}"
        for source in payload.sources
    )
