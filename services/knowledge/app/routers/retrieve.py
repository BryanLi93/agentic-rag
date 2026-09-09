"""只检索、不生成答案的知识库端点。"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.schemas import RetrieveRequest, RetrieveResponse
from app.services.retrieval import retrieve
from app.services.sources import build_sources

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/retrieve", tags=["检索"])


@router.post(
    "",
    response_model=RetrieveResponse,
    summary="只检索知识库并返回结构化来源",
)
async def retrieve_endpoint(
    request: RetrieveRequest,
    db: AsyncSession = Depends(get_db),
) -> RetrieveResponse:
    """执行混合检索、RRF 与可选 Rerank，不调用回答模型。"""

    try:
        retrieved = await retrieve(
            db,
            search_query=request.query,
            top_k=request.top_k,
        )
    except Exception as exc:
        logger.exception("retrieve failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"检索失败：{type(exc).__name__}",
        ) from exc

    return RetrieveResponse(sources=build_sources(retrieved))
