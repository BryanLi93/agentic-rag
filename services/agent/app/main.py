import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import StreamingResponse

from app.schemas import AgentQuery
from app.agent import agent_runtime
from app.streaming import encode_sse, stream_agent_events

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    async with agent_runtime():
        yield


app = FastAPI(
    title="AgenticRAG Agent 服务",
    description="负责 LangGraph 编排，并以流式方式输出回答和工具执行事件。",
    version="0.1.0",
    lifespan=lifespan,
)


@app.post("/agent/stream", summary="流式输出 Agent 回答和工具执行轨迹")
async def agent_stream(request: AgentQuery) -> StreamingResponse:
    async def event_stream():
        events = stream_agent_events(request.question, request.thread_id)
        try:
            try:
                async for event in events:
                    yield event
            finally:
                # 客户端中断或读取失败时，也要关闭这一轮消息流。
                await events.aclose()
        except Exception as exc:
            logger.exception("agent stream failed")
            # 开始流式响应后无法再修改 HTTP 状态码，错误必须作为 SSE 帧返回。
            yield encode_sse({"type": "error", "message": type(exc).__name__})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
