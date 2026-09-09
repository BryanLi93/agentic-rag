"""`/retrieve` 契约的无外部服务单元测试。"""

import os
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("OPENAI_BASE_URL", "http://127.0.0.1:1/v1")
os.environ.setdefault("CHAT_MODEL", "test-chat-model")
os.environ.setdefault("EMBEDDING_MODEL", "test-embedding-model")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg://test:test@127.0.0.1:1/test",
)

from app.routers.retrieve import retrieve_endpoint
from app.models import Chunk, Document
from app.schemas import RetrieveRequest
from app.services.retrieval import RetrievedChunk
from app.services.sources import build_sources


def _retrieved_chunk() -> RetrievedChunk:
    document = Document(
        id=7,
        filename="guide.md",
        content_type="text/markdown",
        byte_size=42,
    )
    chunk = Chunk(
        id=11,
        document_id=7,
        chunk_index=2,
        content="pgvector 支持向量相似度检索。",
        token_count=8,
        embedding=[0.0] * 1024,
    )
    return RetrievedChunk(
        chunk=chunk,
        document=document,
        score=0.02,
        vector_rank=1,
        keyword_rank=2,
        rerank_score=None,
    )


class BuildSourcesTests(unittest.TestCase):
    def test_preserves_source_metadata_and_assigns_reference_id(self) -> None:
        sources = build_sources([_retrieved_chunk()])

        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0].id, 1)
        self.assertEqual(sources[0].chunk_id, 11)
        self.assertEqual(sources[0].document_id, 7)
        self.assertEqual(sources[0].document_filename, "guide.md")
        self.assertEqual(sources[0].chunk_index, 2)
        self.assertEqual(sources[0].content, "pgvector 支持向量相似度检索。")
        self.assertEqual(sources[0].similarity, 0.6)
        self.assertEqual(sources[0].vector_rank, 1)
        self.assertEqual(sources[0].keyword_rank, 2)


class RetrieveEndpointTests(unittest.IsolatedAsyncioTestCase):
    @patch("app.routers.retrieve.retrieve", new_callable=AsyncMock)
    async def test_returns_structured_sources(self, retrieve_mock: AsyncMock) -> None:
        db = AsyncMock(spec=AsyncSession)
        retrieve_mock.return_value = [_retrieved_chunk()]

        response = await retrieve_endpoint(
            RetrieveRequest(query="pgvector", top_k=3),
            db=db,
        )

        retrieve_mock.assert_awaited_once_with(
            db,
            search_query="pgvector",
            top_k=3,
        )
        self.assertEqual(response.sources[0].chunk_id, 11)

    @patch("app.routers.retrieve.retrieve", new_callable=AsyncMock)
    async def test_maps_retrieval_failure_to_502(
        self,
        retrieve_mock: AsyncMock,
    ) -> None:
        retrieve_mock.side_effect = RuntimeError("private detail")
        db = AsyncMock(spec=AsyncSession)

        with self.assertLogs("app.routers.retrieve", level="ERROR"):
            with self.assertRaises(HTTPException) as caught:
                await retrieve_endpoint(
                    RetrieveRequest(query="pgvector"),
                    db=db,
                )

        self.assertEqual(caught.exception.status_code, 502)
        self.assertEqual(caught.exception.detail, "检索失败：RuntimeError")
        self.assertNotIn("private detail", caught.exception.detail)


if __name__ == "__main__":
    unittest.main()
