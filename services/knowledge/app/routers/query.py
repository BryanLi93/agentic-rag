"""
查询端点。
"""
from __future__ import annotations

import logging
import json

from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.responses import StreamingResponse

from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.schemas import QueryRequest, QueryResponse
from app.services.chat import handle_chat, ConversationNotFound, handle_chat_stream

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/query", tags=["问答"])

def _sse(frame: dict) -> str:
    """把一个语义帧编码成一条 SSE 消息。ensure_ascii=False 让中文不被转义。"""
    return f"data: {json.dumps(frame, ensure_ascii=False)}\n\n"

# ---------- 路由 ----------
@router.post(
    "",
    response_model=QueryResponse,  # FastAPI 会用它过滤返回值,只输出 schema 声明的字段
    status_code=status.HTTP_201_CREATED,
    summary="向知识库提问",
)
async def query_endpoint(
    request: QueryRequest,
    db: AsyncSession = Depends(get_db),
) -> QueryResponse:
    """
    薄路由:把编排交给 chat service,这里只负责把领域异常翻译成 HTTP 状态码。
    """
    try:
        return await handle_chat(
            db,
            req_conversation_id=request.conversation_id,
            req_question=request.question,
            req_top_k=request.top_k,
            req_system_prompt=request.system_prompt,
        )
    except ConversationNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")
    except Exception as e:
        logger.exception("query failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"查询失败：{type(e).__name__}",
        )

@router.post(
    "/stream",
    summary="通过 SSE 流式返回知识库回答",
)
async def query_stream_endpoint(
    request: QueryRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    流式查询。帧顺序:sources(1) → token(N) → done(1)。
    错误分两段:开流前(会话不存在/检索失败)返回 HTTP 错误码;
    开流后(生成中途失败)只能塞一条 error 帧。
    """
    agen = handle_chat_stream(
        db,
        req_conversation_id=request.conversation_id,
        req_question=request.question,
        req_top_k=request.top_k,
    )

    # 手动取第一帧:触发会话校验 + 检索。此刻 HTTP 响应还没开始,异常能正常映射状态码。
    try:
        first_frame = await agen.__anext__()
    except ConversationNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")
    except StopAsyncIteration:
        first_frame = None
    except Exception as e:
        logger.exception("stream setup failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"查询失败：{type(e).__name__}",
        )

    async def event_stream():
        if first_frame is not None:
            yield _sse(first_frame)
        try:
            async for frame in agen:
                yield _sse(frame)
        except Exception as e:
            # 已经开流,状态码改不了,只能把错误当成一条数据帧发出去
            logger.exception("stream failed mid-flight")
            yield _sse({"type": "error", "message": type(e).__name__})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # 关掉 nginx 等代理的缓冲,否则流会被堆积一起发
        },
    )
