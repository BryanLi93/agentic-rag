import uuid
import logging
import hashlib
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Message
from app.llm import get_openai_client
from app.config import settings
from app import metrics
from app.services.retrieval import query as run_query, QueryResult
from app.services import conversation as conv_service
from app.schemas import Source, QueryResponse
from app.services.retrieval import retrieve, generate_stream, NO_CONTEXT_ANSWER
from app.services.sources import build_sources
from app.cache import cache_get_json, cache_set_json

logger = logging.getLogger(__name__)


class ConversationNotFound(Exception):
    """请求指定了 conversation_id 但库里不存在;由 router 映射成 404。"""

REWRITE_SYSTEM_PROMPT = """你是一个问题改写助手。根据对话历史,把用户的最新问题改写成一个不依赖上下文、能独立理解的完整问题。

规则:
- 消解所有指代(它/这个/那个等),替换成具体名词
- 补全省略的主语和宾语
- 如果最新问题本身已经完整独立,原样返回
- 只输出改写后的问题本身,不要解释,不要加引号,不要回答问题"""

REWRITE_USER_PROMPT_TEMPLATE = """
根据用户当前问题和之前的聊天记录，生成完整的问题
---
当前问题：{question}
---
聊天记录：{messages}

"""

ANSWER_CACHE_TTL = 60 * 60   # 1 小时:答案随知识库更新过期,TTL 是正确性折中

# ---------- 内部函数 ----------

async def _rewrite_query(question: str, recent_messages: list[Message]) -> str:
    # 查询重写
    client = get_openai_client()
    messages = [f"{m.role}:{m.content}" for m in recent_messages]

    user_prompt = REWRITE_USER_PROMPT_TEMPLATE.format(question=question, messages="\n".join(messages))
    response = await client.chat.completions.create(
        model=settings.chat_model,
        messages=[
            {"role": "system", "content": REWRITE_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.1,
        max_tokens=256,
        # Qwen3.5 思考模型,查询改写更不需要思考链(256 token 根本不够它想)
        extra_body={"enable_thinking": False},
    )
    metrics.record_usage(settings.chat_model, response.usage)

    content = response.choices[0].message.content
    if not content:
        raise RuntimeError("LLM returned empty response")

    return content.strip()

def _answer_cache_key(text: str, top_k: int) -> str:
    h  = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return f"ans:{settings.chat_model}:{top_k}:{h}"


# ---------- 两条链路共用的编排零件 ----------
async def _prepare(
    db: AsyncSession,
    req_conversation_id: uuid.UUID | None,
    req_question: str,
) -> tuple[list[Message], str]:
    # 会话+历史+改写

    # 1. 解析会话 + 加载历史(只读,不写库)
    recent_messages: list[Message] = []
    if req_conversation_id is not None:
        if not await conv_service.conversation_exists(db, req_conversation_id):
            raise ConversationNotFound(str(req_conversation_id))
        recent_messages = await conv_service.get_recent_messages(db, conversation_id=req_conversation_id)

    # 2. 有历史才改写(第一轮没历史,省一次 LLM 调用)
    search_query = req_question
    if recent_messages:
        search_query = await _rewrite_query(req_question, recent_messages)
        logger.info("rewrite: %r -> %r", req_question, search_query)
    return recent_messages, search_query

async def _persist(
    db: AsyncSession,
    req_conversation_id: uuid.UUID | None,
    req_question: str,
    answer: str,
    sources_payload: list[dict],
) -> uuid.UUID:
   # 5. RAG 成功后才写库:会话 + 两条消息,放进一个事务一次提交
    if req_conversation_id is None:
        conv = await conv_service.create_conversation(db, title=req_question[:50], commit=False)
        conversation_id = conv.id
    else:
        conversation_id = req_conversation_id

    await conv_service.add_message(
        db, conversation_id=conversation_id, role="user",
        content=req_question, commit=False,
    )
    await conv_service.add_message(
        db, conversation_id=conversation_id, role="assistant",
        content=answer, sources=sources_payload,
        commit=False,
    )
    await db.commit()
    return conversation_id

# ---------- 两条对外链路:只差"怎么生成" ----------
async def handle_chat(
    db: AsyncSession,
    req_conversation_id: uuid.UUID | None,
    req_question: str,
    req_top_k: int,
    req_system_prompt: str | None = None,
) -> QueryResponse:
    """
    多轮对话编排:解析会话 → 改写 → 检索生成 →(成功后)落库。

    - 所有 DB 写操作都放在 RAG 成功之后,中途失败一个字都不写,不留空会话。
    - 不在这里管 HTTP 状态码:会话不存在抛 ConversationNotFound,由 router 翻译成 404。
    """
    recent_messages, search_query = await _prepare(db, req_conversation_id, req_question)

    # 3. 检索 + 生成(无 DB 写入)
    # 覆盖了 system_prompt(评测 A/B)时不走缓存:缓存键不含 prompt,
    # 否则 v1/v2 同一问题会撞同一条缓存、读到对方的答案。
    is_cacheable = not recent_messages and req_system_prompt is None
    cache_key = _answer_cache_key(req_question, req_top_k) if is_cacheable else None

    if cache_key:
        cached = await cache_get_json(cache_key)
        if cached is not None:
            logger.info("answer cache HIT")
            sources = [Source(**d) for d in cached["sources"]] # dict -> Source 对象
            conversation_id = await _persist(db, req_conversation_id, req_question, cached["answer"], cached["sources"])
            return QueryResponse(answer=cached["answer"], sources=sources, conversation_id=conversation_id)

    result = await run_query(
        db,
        question=req_question,
        search_query=search_query,
        recent_messages=recent_messages,
        top_k=req_top_k,
        system_prompt=req_system_prompt,
    )
    sources = build_sources(result.sources)
    sources_payload = [s.model_dump() for s in sources]

    if cache_key:
        await cache_set_json(cache_key, { "answer": result.answer, "sources": sources_payload }, ttl=ANSWER_CACHE_TTL)

    conversation_id = await _persist(db, req_conversation_id, req_question, result.answer, sources_payload)

    # 6. 返回
    return QueryResponse(answer=result.answer, sources=sources, conversation_id=conversation_id)

async def handle_chat_stream(
    db: AsyncSession,
    req_conversation_id: uuid.UUID | None,
    req_question: str,
    req_top_k: int,
) -> AsyncIterator[dict]:
    # """流式:sources 整包先发,answer 逐 token 发,done 收尾。写库时机同 handle_chat。"""
    recent_messages, search_query = await _prepare(db, req_conversation_id, req_question)

    is_cacheable = not recent_messages
    cache_key = _answer_cache_key(req_question, req_top_k) if is_cacheable else None

    if cache_key:
        cached = await cache_get_json(cache_key)
        if cached is not None:
            logger.info("answer cache HIT (stream)")
            yield {"type": "sources", "sources": cached["sources"]}
            yield {"type": "token", "text": cached["answer"]}
            conversation_id = await _persist(db, req_conversation_id, req_question, cached["answer"], cached["sources"])
            yield {"type": "done", "conversation_id": str(conversation_id)}
            return

    # 未命中缓存:照旧检索 + 逐 token 生成
    retrieved = await retrieve(db, search_query=search_query, top_k=req_top_k)

    sources = build_sources(retrieved)
    sources_payload = [s.model_dump() for s in sources]
    yield {"type": "sources", "sources": sources_payload}

    if retrieved:
        parts: list[str] = []
        async for token in generate_stream(req_question, retrieved, recent_messages):
            parts.append(token)
            yield {"type": "token", "text": token}
        answer = "".join(parts)
    else:
        answer = NO_CONTEXT_ANSWER
        yield {"type": "token", "text": answer}

    if cache_key:
        await cache_set_json(
            cache_key, { "answer": answer, "sources": sources_payload }, ttl=ANSWER_CACHE_TTL
        )

    conversation_id = await _persist(db, req_conversation_id, req_question, answer, sources_payload)
    yield {"type": "done", "conversation_id": str(conversation_id)}
