"""
文档入库服务。

流程: 文件内容 → 切块 → embedding → 数据库事务写入
"""
from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from dataclasses import dataclass
from app.models import Document, Chunk
from app.chunking import split_text, Chunk as ChunkData
from app.embedding import embed_documents

logger = logging.getLogger(__name__)


@dataclass
class IngestResult:
    """入库结果(供路由层使用)。"""
    document: Document
    chunk_count: int

class EmptyContentError(ValueError):
    """文件内容为空或全是空白。"""

async def ingest_text_file(
    db: AsyncSession,
    *,
    filename: str,
    content_type: str,
    content: str,
    byte_size: int
) -> IngestResult:
    """
        把一份纯文本内容入库。

        Args:
            db: 数据库 session(从 FastAPI 依赖注入获得)
            filename: 文件名(用于元数据)
            content_type: MIME 类型(如 text/plain, text/markdown)
            content: 文本内容(已解码为 str)
            byte_size: 原始字节大小

        Returns:
            IngestResult: 包含 document 实体和 chunk 数量

        Raises:
            EmptyContentError: 内容为空
            其他异常: embedding 失败 / 数据库错误,事务自动回滚
    """
    logger.info("ingesting file: %s (%d bytes)", filename, byte_size)

    # 1. 切块
    chunks_data: list[ChunkData] = split_text(content)
    if not chunks_data:
        raise EmptyContentError(f"file {filename} produced no chunks")
    logger.info("split into %d chunks", len(chunks_data))

    # 2. 批量 embedding
    texts = [c.content for c in chunks_data]
    embeddings = await embed_documents(texts)

    assert len(embeddings) == len(texts), (
        f"embedding count mismatch: {len(embeddings)} vs {len(chunks_data)}"
    )

    # 3. 数据库事务写入
    document = Document(
        filename=filename,
        content_type=content_type,
        byte_size=byte_size
    )
    db.add(document)
    await db.flush() # 触发 INSERT 拿到自增 id,不提交事务

    chunk_records = [
        Chunk(
            document_id=document.id,
            chunk_index=cd.index,
            content=cd.content,
            token_count=cd.token_count,
            embedding=emb,
        )
        for cd, emb in zip(chunks_data, embeddings)
    ]
    db.add_all(chunk_records)
    await db.commit()

    logger.info(
        "ingested document %d (%s) with %d chunks",
        document.id, filename, len(chunk_records),
    )

    return IngestResult(document=document,chunk_count=len(chunk_records))
