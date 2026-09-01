from pydantic import BaseModel, Field


class AgentQuery(BaseModel):
    question: str = Field(min_length=1, max_length=1000)


class KnowledgeSource(BaseModel):
    document_filename: str
    content: str


class KnowledgeQueryResponse(BaseModel):
    sources: list[KnowledgeSource]
