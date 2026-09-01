import uuid

from fastapi import APIRouter, status, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.schemas import (
    ConversationCreate,
    ConversationDetail,
    ConversationSummary,
    MessageOut
)
from app.services import conversation as conv_service

router = APIRouter(prefix="/conversations", tags=["会话"])

@router.post("", response_model=ConversationSummary, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    request: ConversationCreate,
    db: AsyncSession = Depends(get_db)
) -> ConversationSummary:
    conv = await conv_service.create_conversation(db, title=request.title)
    return ConversationSummary.model_validate(conv)

@router.get("", response_model=list[ConversationSummary])
async def list_conversations(
    db: AsyncSession = Depends(get_db),
) -> list[ConversationSummary]:
    convs = await conv_service.list_conversations(db)
    return [ConversationSummary.model_validate(c) for c in convs]


@router.get("/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(
    conversation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> ConversationDetail:
    conv = await conv_service.get_conversation(db, conversation_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="会话不存在")

    return ConversationDetail.model_validate(conv)

@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db)
):
    deleted = await conv_service.delete_conversation(db, conversation_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="会话不存在")
    # 204 No Content,不返回 body
