"""端到端测试 ingest 服务。运行:python -m scripts.test_ingest"""
import asyncio
import logging
from pathlib import Path
from sqlalchemy import select, func, delete

from app.db import AsyncSessionLocal
from app.services.ingest import ingest_text_file
from app.models import Document, Chunk

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

TEST_DATA_DIR = Path(__file__).resolve().parent / "test_data" / "documents"
LEGACY_SAMPLE_FILENAMES = {"python_intro.md"}


def load_sample_documents() -> list[Path]:
    documents = sorted(TEST_DATA_DIR.glob("*.md"))
    if not documents:
        raise FileNotFoundError(f"no sample documents found in {TEST_DATA_DIR}")
    return documents


async def main():
    sample_documents = load_sample_documents()

    async with AsyncSessionLocal() as db:
        # 只清理本测试脚本管理的样例文档，避免重复运行导致相同 chunks 反复命中。
        sample_filenames = sorted({path.name for path in sample_documents} | LEGACY_SAMPLE_FILENAMES)
        await db.execute(delete(Document).where(Document.filename.in_(sample_filenames)))
        await db.commit()

        created_document_ids: list[int] = []
        total_created_chunks = 0

        for path in sample_documents:
            sample_text = path.read_text(encoding="utf-8")
            result = await ingest_text_file(
                db,
                filename=path.name,
                content_type="text/markdown",
                content=sample_text,
                byte_size=len(sample_text.encode("utf-8")),
            )
            created_document_ids.append(result.document.id)
            total_created_chunks += result.chunk_count

            print(f"\n✓ Created document id={result.document.id}")
            print(f"  filename={result.document.filename}")
            print(f"  chunks={result.chunk_count}")

        print(
            f"\nSample ingest complete: "
            f"{len(created_document_ids)} documents, {total_created_chunks} chunks"
        )

        # 验证查询
        doc_count = await db.scalar(select(func.count(Document.id)))
        chunk_count = await db.scalar(select(func.count(Chunk.id)))
        print(f"\nDB state: {doc_count} documents, {chunk_count} chunks total")

        # 抽查一个 chunk
        first_chunk = await db.scalar(
            select(Chunk)
            .where(Chunk.document_id.in_(created_document_ids))
            .order_by(Chunk.document_id, Chunk.chunk_index)
            .limit(1)
        )
        if first_chunk:
            embedding_list = first_chunk.embedding.to_list()
            print(f"\nFirst chunk:")
            print(f"  index={first_chunk.chunk_index}")
            print(f"  tokens={first_chunk.token_count}")
            print(f"  embedding dim={len(embedding_list)}")
            print(f"  embedding preview={embedding_list[:5]}")
            print(f"  content preview: {first_chunk.content[:50]}...")


if __name__ == "__main__":
    asyncio.run(main())
