import logging

from fastapi import FastAPI
from fastapi.responses import StreamingResponse

from app.schemas import AgentQuery
from app.streaming import encode_sse, stream_agent_events

logger = logging.getLogger(__name__)

app = FastAPI(
    title="AgenticRAG Agent 服务",
    description="负责 LangGraph 编排，并以流式方式输出回答和工具执行事件。",
    version="0.1.0",
)


@app.post("/agent/stream", summary="流式输出 Agent 回答和工具执行轨迹")
async def agent_stream(request: AgentQuery) -> StreamingResponse:
    async def event_stream():
        try:
            async for event in stream_agent_events(request.question):
                yield event
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
