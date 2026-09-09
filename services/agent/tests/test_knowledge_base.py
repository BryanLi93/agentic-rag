"""验证 ToolMessage 的正文、artifact 与 Knowledge HTTP 契约，无外部请求。"""

import json
import os
import unittest
from unittest.mock import patch

import httpx
from langchain_core.messages import ToolMessage
from pydantic import ValidationError

with patch.dict(os.environ, {
    "OPENAI_API_KEY": "test-key",
    "OPENAI_BASE_URL": "http://127.0.0.1:1/v1",
    "CHAT_MODEL": "test-model",
}):
    from app.tools.knowledge_base import search_knowledge_base


class KnowledgeToolTests(unittest.IsolatedAsyncioTestCase):
    async def invoke_tool(self, transport: httpx.MockTransport) -> ToolMessage:
        client = httpx.AsyncClient(
            base_url="http://knowledge.test", transport=transport,
        )
        with patch("app.tools.knowledge_base.httpx.AsyncClient", return_value=client):
            result = await search_knowledge_base.ainvoke({
                "type": "tool_call",
                "name": "search_knowledge_base",
                "id": "call-1",
                "args": {"query": "pgvector"},
            })
        self.assertIsInstance(result, ToolMessage)
        return result

    async def test_retrieve_request_and_complete_artifact(self) -> None:
        sources = [{
            "id": 4,
            "chunk_id": 11,
            "document_id": 7,
            "document_filename": "guide.md",
            "chunk_index": 2,
            "content": "pgvector 支持向量检索。",
            "similarity": 0.6,
            "vector_rank": 1,
            "keyword_rank": None,
            "rerank_score": 0.91,
        }]
        requests: list[httpx.Request] = []

        def respond(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            self.assertEqual(request.method, "POST")
            self.assertEqual(request.url.path, "/retrieve")
            self.assertEqual(json.loads(request.content), {"query": "pgvector", "top_k": 3})
            return httpx.Response(200, json={"sources": sources})

        result = await self.invoke_tool(httpx.MockTransport(respond))
        self.assertEqual(len(requests), 1)
        self.assertEqual(result.tool_call_id, "call-1")
        self.assertEqual(result.content, "[4] 文档名：guide.md\npgvector 支持向量检索。")
        self.assertEqual(result.artifact, {"sources": sources})
        json.dumps(result.artifact)  # artifact 可直接用于 JSON/SSE 序列化。

    async def test_empty_sources_still_returns_artifact(self) -> None:
        result = await self.invoke_tool(httpx.MockTransport(
            lambda request: httpx.Response(200, json={"sources": []}),
        ))
        self.assertEqual(result.content, "知识库中没有检索到相关内容。")
        self.assertEqual(result.artifact, {"sources": []})

    async def test_http_failure_propagates(self) -> None:
        with self.assertRaises(httpx.HTTPStatusError):
            await self.invoke_tool(httpx.MockTransport(
                lambda request: httpx.Response(502, json={"detail": "检索失败"}),
            ))

    async def test_timeout_propagates(self) -> None:
        def timeout(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("timeout", request=request)

        with self.assertRaises(httpx.ReadTimeout):
            await self.invoke_tool(httpx.MockTransport(timeout))

    async def test_incomplete_source_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            await self.invoke_tool(httpx.MockTransport(
                lambda request: httpx.Response(200, json={"sources": [{
                    "document_filename": "guide.md", "content": "missing IDs",
                }]}),
            ))


if __name__ == "__main__":
    unittest.main()
