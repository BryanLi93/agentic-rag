"""检索结果到对外 citation schema 的统一映射。"""

from app.schemas import Source
from app.services.retrieval import RetrievedChunk


def build_sources(retrieved: list[RetrievedChunk]) -> list[Source]:
    """按检索顺序分配引用编号，并保留完整来源元数据。"""

    return [
        Source(
            id=index,
            chunk_id=item.chunk.id,
            document_id=item.document.id,
            document_filename=item.document.filename,
            chunk_index=item.chunk.chunk_index,
            content=item.chunk.content,
            similarity=round(item.similarity, 4),
            vector_rank=item.vector_rank,
            keyword_rank=item.keyword_rank,
            rerank_score=item.rerank_score,
        )
        for index, item in enumerate(retrieved, start=1)
    ]
