from typing import Any
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import (
    String, Integer, DateTime, func, ForeignKey, Text,
    Computed, Index, Uuid
)
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.dialects.postgresql import JSONB
from datetime import datetime
from pgvector.sqlalchemy import HALFVEC
from app.config import settings
import uuid


class Base(DeclarativeBase):
    pass

class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String(512))
    content_type: Mapped[str] = mapped_column(String(128))
    byte_size: Mapped[int] = mapped_column(Integer)
    create_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    chunks: Mapped[list["Chunk"]] = relationship(
        back_populates="document",
    )

class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"),
        index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer) # 在文档内的顺序
    content: Mapped[str] = mapped_column(Text)
    token_count: Mapped[int] = mapped_column(Integer)
    embedding: Mapped[list[float]] = mapped_column(HALFVEC(settings.embedding_dim))

    document: Mapped["Document"] = relationship(back_populates="chunks")

    # PostgreSQL maintains this search vector from content for keyword retrieval.
    content_tsv: Mapped[Any] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('chinese_zh', content)", persisted=True)
    )

     # GIN 索引,加速 @@ 查询
    __table_args__ = (
        Index(
          "idx_chunks_content_tsv",
          "content_tsv",
          postgresql_using="gin",
        ),
    )

class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    title: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        # 为什么 order_by="Message.id" 而不是 created_at？
        # 这是个隐藏的坑。PostgreSQL 里 func.now() 返回的是事务开始时间,不是语句执行时间。
        order_by="Message.id",
    )

class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"),
        index=True
    )
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    sources_json: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    conversation: Mapped["Conversation"] = relationship(
        back_populates="messages"
    )

    @property
    def sources(self):
        return self.sources_json
