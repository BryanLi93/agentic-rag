from pydantic import BaseModel, Field


class AgentQuery(BaseModel):
    question: str = Field(min_length=1, max_length=1000)


class KnowledgeSource(BaseModel):
    """与 Knowledge /retrieve 的 Source 契约保持一致。"""

    id: int
    chunk_id: int
    document_id: int
    document_filename: str
    chunk_index: int
    content: str
    similarity: float
    vector_rank: int | None = None
    keyword_rank: int | None = None
    rerank_score: float | None = None


class KnowledgeRetrieveResponse(BaseModel):
    sources: list[KnowledgeSource]
