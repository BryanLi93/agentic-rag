"""
API 请求/响应 schemas。

设计原则:
- 输入用 Request,输出用 Response,清晰区分
- 内部 ORM 模型(models.py)和 API schema(这里)解耦
- Citation metadata 通过 Source 保持结构化,不嵌入 answer 文本
"""

from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict
import uuid

# ---------- Upload 端点 ----------

class UploadResponse(BaseModel):
    """文件上传成功的响应。"""
    document_id: int = Field(description="新建文档的主键")
    filename: str = Field(description="文件名")
    chunk_count: int = Field(description="切分后的文本块数量")
    created_at: datetime = Field(description="入库时间")

# ---------- Retrieve 端点 ----------

class RetrieveRequest(BaseModel):
    """只检索知识库，不生成答案。"""
    query: str = Field(
        min_length=1,
        max_length=1000,
        description="检索查询,1-1000 字符",
    )
    top_k: int = Field(
        default=5,
        ge=1,
        le=20,
        description="检索返回的文本块数量,默认 5",
    )


# ---------- Query 端点 ----------

class QueryRequest(BaseModel):
    """用户提问。"""
    question: str = Field(
        min_length=1,
        max_length=1000,
        description="用户问题,1-1000 字符",
    )
    top_k: int = Field(
        default=5,
        ge=1,
        le=20,
        description="检索返回的文本块数量,默认 5",
    )
    conversation_id: uuid.UUID | None = Field(
        default=None,
        description="会话 ID,不传则创建新会话",
    )
    system_prompt: str | None = Field(
        default=None,
        description="覆盖默认系统提示词（用于 Prompt A/B 评测）；不传则使用服务端默认值",
    )

class Source(BaseModel):
    """检索到的文本块引用信息。"""
    id: int = Field(description="本次检索的引用编号,可对应后续答案中的 [n] 标记")
    chunk_id: int = Field(description="文本块主键")
    document_id: int = Field(description="所属文档 ID")
    document_filename: str = Field(description="文档名")
    chunk_index: int = Field(description="文本块在文档内的顺序")
    content: str = Field(description="文本块内容")
    similarity: float = Field(description="相似度分数 0-1,越高越相关")

    vector_rank: int | None = None
    keyword_rank: int | None = None
    rerank_score: float | None = None


class RetrieveResponse(BaseModel):
    """不经过答案生成的结构化检索结果。"""
    sources: list[Source] = Field(description="按检索相关性排序的文本块列表")


class QueryResponse(BaseModel):
    """RAG 答案。"""
    answer: str = Field(description="基于检索内容生成的答案")
    sources: list[Source] = Field(description="答案引用的文本块列表")
    conversation_id: uuid.UUID

# ---------- Conversation 端点 ----------
class ConversationCreate(BaseModel):
    title: str | None = Field(default=None, max_length=256)

class ConversationSummary(BaseModel):
    """会话列表项(不含消息)。"""
    id: uuid.UUID
    title: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class MessageOut(BaseModel):
    """单条消息。"""
    id: int
    role: str
    content: str
    sources: list[Source] | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class ConversationDetail(BaseModel):
    """会话详情(含全部消息)。"""
    id: uuid.UUID
    title: str | None
    created_at: datetime
    messages: list[MessageOut]

    model_config = ConfigDict(from_attributes=True)
