import json
from collections.abc import AsyncIterator, Mapping

from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage

from app.agent import agent


def encode_sse(frame: Mapping[str, object]) -> str:
    """将一个语义帧编码为 SSE 消息。"""

    return f"data: {json.dumps(frame, ensure_ascii=False)}\n\n"


def _content_text(content: object) -> str:
    return content if isinstance(content, str) else str(content)


async def stream_agent_events(question: str) -> AsyncIterator[str]:
    """将 LangGraph 消息更新转换为前端使用的 SSE 接口格式。"""

    async for mode, payload in agent.astream(
        {"messages": [HumanMessage(question)]},
        stream_mode=["updates", "messages"],
    ):
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

    yield encode_sse({"type": "done"})
