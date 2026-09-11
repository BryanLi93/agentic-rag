"""验证 Agent SSE 转换契约；模拟事件流，不调用模型或 Knowledge 服务。"""

import importlib
import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage
from pydantic import ValidationError

with patch.dict(os.environ, {
    "OPENAI_API_KEY": "test-key",
    "OPENAI_BASE_URL": "http://127.0.0.1:1/v1",
    "CHAT_MODEL": "test-model",
}):
    streaming = importlib.import_module("app.streaming")


SOURCE = {
    "id": 4,
    "chunk_id": 11,
    "document_id": 7,
    "document_filename": "RAG.md",
    "chunk_index": 2,
    "content": "召回与精排。",
    "similarity": 0.6,
    "vector_rank": 1,
    "keyword_rank": None,
    "rerank_score": 0.91,
}


def tool_message(artifact: object, call_id: str = "call-1", **kwargs: object) -> ToolMessage:
    return ToolMessage(
        content="[4] 召回与精排。", artifact=artifact,
        tool_call_id=call_id, name="search_knowledge_base", **kwargs,
    )


class StreamingTests(unittest.IsolatedAsyncioTestCase):
    async def collect(self, events: list[tuple[str, object]]) -> list[dict[str, object]]:
        async def event_stream(*args: object, **kwargs: object):
            for event in events:
                yield event

        with patch.object(streaming, "get_agent", return_value=SimpleNamespace(astream=event_stream)):
            frames = [frame async for frame in streaming.stream_agent_events("什么是 RAG？", "test-stream")]
        for frame in frames:
            self.assertTrue(frame.startswith("data: "))
            self.assertTrue(frame.endswith("\n\n"))
        return [json.loads(frame[6:]) for frame in frames]

    async def test_sources_preserve_artifact_and_step_token_contract(self) -> None:
        message = tool_message({"sources": [SOURCE]})
        frames = await self.collect([
            ("updates", {"model": {"messages": [AIMessage(content="", tool_calls=[{
                "name": "search_knowledge_base", "args": {"query": "RAG"}, "id": "call-1",
            }])]}}),
            ("updates", {"tools": {"messages": [message]}}),
            ("messages", (message, {})),
            ("messages", (AIMessageChunk(content="答案[4]"), {})),
        ])
        self.assertEqual([f["type"] for f in frames], ["step", "sources", "step", "token", "done"])
        self.assertEqual(frames[0]["status"], "running")
        self.assertEqual(frames[1], {
            "type": "sources", "tool_call_id": "call-1", "sources": [SOURCE],
        })
        self.assertEqual(frames[2]["output"], message.content)
        self.assertEqual(frames[2]["status"], "done")
        self.assertEqual(frames[3], {"type": "token", "content": "答案[4]"})

    async def test_empty_sources_are_emitted(self) -> None:
        frames = await self.collect([("updates", {"tools": {
            "messages": [tool_message({"sources": []})],
        }})])
        self.assertEqual(frames[0], {"type": "sources", "tool_call_id": "call-1", "sources": []})

    async def test_no_retrieval_has_no_sources(self) -> None:
        frames = await self.collect([("messages", (AIMessageChunk(content="你好"), {}))])
        self.assertEqual(frames, [{"type": "token", "content": "你好"}, {"type": "done", "thread_id": "test-stream"}])

    async def test_missing_artifact_other_tool_and_error_are_ignored(self) -> None:
        messages = [
            tool_message(None),
            ToolMessage(content="其他工具", name="other", tool_call_id="call-2", artifact={"sources": [SOURCE]}),
            tool_message({"sources": [SOURCE]}, "call-3", status="error"),
        ]
        frames = await self.collect([("updates", {"tools": {"messages": messages}})])
        self.assertEqual([f["type"] for f in frames], ["step", "step", "step", "done"])

    async def test_multiple_calls_keep_separate_sources_and_original_ids(self) -> None:
        frames = await self.collect([("updates", {"tools": {"messages": [
            tool_message({"sources": [SOURCE]}, "call-1"),
            tool_message({"sources": [dict(SOURCE, chunk_id=12)]}, "call-2"),
        ]}})])
        sources = [f for f in frames if f["type"] == "sources"]
        self.assertEqual(sources, [
            {"type": "sources", "tool_call_id": "call-1", "sources": [SOURCE]},
            {"type": "sources", "tool_call_id": "call-2", "sources": [dict(SOURCE, chunk_id=12)]},
        ])

    async def test_invalid_artifact_fails_validation(self) -> None:
        with self.assertRaises(ValidationError):
            await self.collect([("updates", {"tools": {
                "messages": [tool_message({"sources": [{"id": 1}]})],
            }})])

    async def test_router_emits_error_without_normal_done_for_invalid_artifact(self) -> None:
        from app.main import agent_stream
        from app.schemas import AgentQuery

        async def event_stream(*args: object, **kwargs: object):
            yield "updates", {"tools": {"messages": [tool_message({"sources": [{}]})]}}

        with patch.object(streaming, "get_agent", return_value=SimpleNamespace(astream=event_stream)):
            response = await agent_stream(AgentQuery(question="什么是 RAG？"))
            with self.assertLogs("app.main", level="ERROR"):
                frames = [json.loads(frame[6:]) async for frame in response.body_iterator]
        self.assertEqual(response.media_type, "text/event-stream")
        self.assertEqual(frames, [{"type": "error", "message": "ValidationError"}])


if __name__ == "__main__":
    unittest.main()
