import json
from collections.abc import AsyncIterator, Mapping
from uuid import uuid4

from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage

from app.agent import get_agent
from app.schemas import KnowledgeRetrieveResponse


def encode_sse(frame: Mapping[str, object]) -> str:
    """将一个语义帧编码为 SSE 消息。"""

    return f"data: {json.dumps(frame, ensure_ascii=False)}\n\n"


def _content_text(content: object) -> str:
    return content if isinstance(content, str) else str(content)


_active_threads: set[str] = set()


class ThreadBusyError(RuntimeError):
    """同一进程内，同一会话不能同时执行两轮请求。"""


async def stream_agent_events(question: str, thread_id: str | None = None) -> AsyncIterator[str]:
    """按会话运行 Agent，禁止并发写入同一份 checkpoint。"""

    resolved_thread_id = thread_id or str(uuid4())
    if resolved_thread_id in _active_threads:
        raise ThreadBusyError("该会话仍在生成回答，请等待结束后再发送。")
    _active_threads.add(resolved_thread_id)
    events = _stream_agent_events(question, resolved_thread_id)
    try:
        async for event in events:
            yield event
    finally:
        try:
            # 先关闭内层消息流，等待底层 Agent 清理完毕。
            await events.aclose()
        finally:
            _active_threads.discard(resolved_thread_id)


async def _stream_agent_events(question: str, thread_id: str) -> AsyncIterator[str]:
    """将 LangGraph 消息更新转换为前端使用的 SSE 接口格式。"""

    agent_events = get_agent().astream(
        {"messages": [HumanMessage(question)]},
        config={"configurable": {"thread_id": thread_id}},
        stream_mode=["updates", "messages"],
    )
    try:
        async for mode, payload in agent_events:
            if mode == "updates":
                for data in payload.values():
                    for message in data.get("messages", []):
                        if isinstance(message, AIMessage) and message.tool_calls:
                            for tool_call in message.tool_calls:
                                yield encode_sse(
                                    {
                                        "type": "step",
                                        "id": tool_call["id"],
                                        "tool": tool_call["name"],
                                        "status": "running",
                                        "input": tool_call["args"],
                                    }
                                )
                        elif isinstance(message, ToolMessage):
                            if (
                                message.name == "search_knowledge_base"
                                and message.status != "error"
                                and message.artifact is not None
                            ):
                                sources = KnowledgeRetrieveResponse.model_validate(
                                    message.artifact
                                )
                                yield encode_sse(
                                    {
                                        "type": "sources",
                                        "tool_call_id": message.tool_call_id,
                                        **sources.model_dump(mode="json"),
                                    }
                                )
                            yield encode_sse(
                                {
                                    "type": "step",
                                    "id": message.tool_call_id,
                                    "tool": message.name or "unknown_tool",
                                    "status": "done",
                                    "output": _content_text(message.content),
                                }
                            )

            elif mode == "messages":
                chunk, _metadata = payload
                # messages 模式也会产生 ToolMessage；回答流中只接收 AIMessageChunk。
                if isinstance(chunk, AIMessageChunk) and chunk.content:
                    yield encode_sse(
                        {"type": "token", "content": _content_text(chunk.content)}
                    )

    finally:
        # 显式关闭最底层生成器，不能只关闭外层 SSE 转发器。
        await agent_events.aclose()

    yield encode_sse({"type": "done", "thread_id": thread_id})
