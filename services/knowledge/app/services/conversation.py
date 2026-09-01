import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models import Conversation, Message

async def create_conversation(
    db: AsyncSession,
    title: str | None = None,
    commit: bool = True
) -> Conversation:
    """创建新会话。commit=False 时只 flush 拿到 id,由调用方统一提交(用于和消息同一事务)。"""
    conv = Conversation(title=title)
    db.add(conv)
    if commit:
        await db.commit()
        await db.refresh(conv) # 刷新拿到数据库生成的 id 和 created_at
    else:
        await db.flush()       # 拿到 python 端生成的 id,但不提交
    return conv

async def delete_conversation(
    db: AsyncSession,
    conversation_id: uuid.UUID
) -> bool:
    """删除会话(级联删除消息)。返回是否删除成功。"""
    conv = await db.get(Conversation, conversation_id)
    if conv is None:
        return False
    await db.delete(conv)
    await db.commit()
    return True


async def get_conversation(
    db: AsyncSession,
    conversation_id: uuid.UUID
) -> Conversation | None:
    """获取会话 + 全部消息(按时间顺序)。"""
    stmt = (
        select(Conversation)
        .options(selectinload(Conversation.messages))
        .where(Conversation.id == conversation_id)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()

async def list_conversations(
    db: AsyncSession
) -> list[Conversation]:
    """列出所有会话(最新在前,不含消息)。"""
    stmt = select(Conversation).order_by(Conversation.created_at.desc())
    result = await db.execute(stmt)
    return list(result.scalars().all())

async def add_message(
    db: AsyncSession,
    conversation_id: uuid.UUID,
    role: str,
    content: str,
    sources: list[dict] | None = None,
    commit: bool = True
) -> Message:
    """追加一条消息。commit=False 时由调用方统一提交(用于一次写多条)。"""
    msg = Message(
        conversation_id=conversation_id,
        role=role,
        content=content,
        sources_json=sources
    )
    db.add(msg)
    if commit:
        await db.commit()
    return msg

async def conversation_exists(
    db: AsyncSession,
    conversation_id: uuid.UUID
) -> bool:
    """轻量检查会话是否存在(不加载消息)。"""
    conv = await db.get(Conversation, conversation_id)
    return conv is not None

async def get_recent_messages(
    db: AsyncSession,
    conversation_id: uuid.UUID,
    limit: int = 6
) -> list[Message]:
    # 查询最近 limit 条消息
    stmt = (select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.id.desc()) # 先按 id 倒序,LIMIT 砍掉老的、留最新 6 条
        .limit(limit))
    result = await db.execute(stmt)
    return list(reversed(result.scalars().all())) # 再翻成正序给 prompt 用
