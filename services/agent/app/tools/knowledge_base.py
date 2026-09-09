import httpx
from langchain_core.tools import tool

from app.config import settings
from app.schemas import KnowledgeRetrieveResponse


@tool(response_format="content_and_artifact")
async def search_knowledge_base(query: str) -> tuple[str, dict[str, object]]:
    """检索内部 AI 学习笔记，返回带引用编号的依据。

    AI 知识问题优先使用，包括 RAG、Embedding、分块、混合检索、RRF、
    Rerank 和 Agent；用户明确要求查询笔记或知识库时也使用。
    返回内容可能不足以回答问题，应判断相关性，不要编造引用。
    """

    async with httpx.AsyncClient(
        base_url=settings.rag_api_base.rstrip("/"),
        timeout=settings.rag_timeout_seconds,
    ) as client:
        response = await client.post(
            "/retrieve",
            json={"query": query, "top_k": 3},
        )
        response.raise_for_status()

    payload = KnowledgeRetrieveResponse.model_validate(response.json())
    # 正文供模型引用；artifact 保留完整来源，供后续 SSE 和应用层使用。
    artifact = payload.model_dump(mode="json")
    if not payload.sources:
        return "知识库中没有检索到相关内容。", artifact

    content = "\n\n".join(
        f"[{source.id}] 文档名：{source.document_filename}\n{source.content}"
        for source in payload.sources
    )
    return content, artifact
