"""
检索 + 生成服务。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
import re
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text as sql_text
from sqlalchemy.orm import selectinload

from app.embedding import embed_query
from app.llm import get_openai_client
from app.models import Chunk, Document, Message
from app.config import settings
from app.rerank import rerank as do_rerank
from app import metrics

logger = logging.getLogger(__name__)

# ---------- 常量 ----------

DEFAULT_TOP_K = 5

CANDIDATES_MULTIPLIER = 4   # 每路检索召回 top_k * 4 个候选,留出 RRF 融合空间
RRF_K = 60                  # RRF 平滑常数,标准取值

RERANK_CANDIDATES = 20      # 送给 reranker 的候选数(从 RRF 融合后取这么多)
ENABLE_RERANK = True        # 开关,方便对比测试

# 检索结果不足时,直接告诉用户
NO_CONTEXT_ANSWER = "根据现有知识库,我没有找到能回答这个问题的相关内容。"

SYSTEM_PROMPT = """你是一个严格基于上下文回答问题的助手。

你必须遵守的规则:

1. 只能使用下方"上下文"中提供的信息回答问题。每条上下文都有编号 [1]、[2]、[3] 等。
2. 在回答中引用具体信息时,必须在引用内容后立刻标注来源编号,格式为 [n] 或 [n][m]。例如:
   - 正确:"FastAPI 是一个现代 Python web 框架 [1],由 Sebastian 开发 [2]。"
   - 错误:"FastAPI 是一个现代 Python web 框架,由 Sebastian 开发。"(没标注)
3. 一句话可以引用多个来源:"RAG 包含检索和生成两个阶段 [1][3]。"
4. 如果上下文中没有足够信息回答问题,直接回答"根据现有知识库,我没有找到能回答这个问题的相关内容。"——不要标注任何编号,不要编造,不要使用上下文以外的常识。
5. 回答简洁、准确,不要重复问题本身。
6. 如果提供了"历史聊天记录",它仅用于帮助你理解当前问题的指代和背景,不是事实来源,也不能作为引用对象;事实和引用编号一律只能来自"上下文"。

请严格遵守以上规则,特别是引用标注。"""

USER_PROMPT_TEMPLATE = """
上下文:
---
{context}
---

问题: {question}

请基于上下文回答，并标注引用编号 [n]。"""

HISTORY_PROMPT_TEMPLATE = """历史聊天记录:
---
{history}
---

"""

# ---------- 内部数据结构 ----------
@dataclass
class RetrievedChunk:
    """检索到的 chunk + 元数据。"""
    chunk: Chunk
    document: Document
    score: float                # RRF 融合分数
    vector_rank: int | None     # 在向量路径里的名次(1-based),没召回到则 None
    keyword_rank: int | None    # 在关键词路径里的名次,没召回到则 None
    rerank_score: float | None = None

    @property
    def similarity(self) -> float:
        """UI 友好的相关度分数(0-1,从 RRF score 派生)。"""
        # RRF 单路第一名 ≈ 0.0164,两路都命中第一名 ≈ 0.0328
        # 乘以 30 放大到 UI 友好的 0-1 区间
        return min(1.0, self.score * 30)

@dataclass
class QueryResult:
    """完整查询结果。"""
    answer: str
    sources: list[RetrievedChunk]


async def _retrieve_by_vector(
    db: AsyncSession,
    query_vector: list[float],
    limit: int
) -> dict[int, int]:
    """向量检索：返回 {chunk_id: rank},rank 从 1 开始。"""
    stmt = (
        select(Chunk.id)
        .order_by(Chunk.embedding.cosine_distance(query_vector))
        .limit(limit)
    )
    result = await db.execute(stmt)
    return {
        chunk_id: rank for rank, (chunk_id,) in enumerate(result.all(), start=1)
    }


async def _retrieve_by_keyword(
    db: AsyncSession,
    question: str,
    limit: int
) -> dict[int, int]:
    """关键词检索：全文搜索,返回 {chunk_id: rank}。"""
    sql = sql_text("""
        WITH parsed AS (
            SELECT NULLIF(
                array_to_string(
                    tsvector_to_array(to_tsvector('chinese_zh', :q)),
                    ' | '
                ),
                ''
            ) AS or_query
        )
        SELECT chunks.id
        FROM chunks, parsed
        WHERE parsed.or_query IS NOT NULL
          AND chunks.content_tsv @@ to_tsquery('chinese_zh', parsed.or_query)
        ORDER BY ts_rank_cd(
            chunks.content_tsv,
            to_tsquery('chinese_zh', parsed.or_query)
        ) DESC
        LIMIT :k
    """)
    result = await db.execute(sql, { "q": question, "k": limit })
    return {
        row[0]: rank for rank, row in enumerate(result.all(), start=1)
    }

async def _rrf_fuse(
    vector_rankings: dict[int, int],
    keyword_rankings: dict[int, int],
    top_k: int
) -> list[tuple[int, float, int | None, int | None]]:
    """
    RRF 融合：RRF 算法融合两路排名。
    返回 [(chunk_id, rrf_score, vector_rank, keyword_rank), ...],按分数降序。
    """
    all_ids = set(vector_rankings) | set(keyword_rankings)
    scored = []
    for chunk_id in all_ids:
        v_rank = vector_rankings.get(chunk_id)
        k_rank = keyword_rankings.get(chunk_id)
        score = 0.0
        if v_rank is not None:
            score += 1.0 / (RRF_K + v_rank)
        if k_rank is not None:
            score += 1.0 / (RRF_K + k_rank)
        scored.append((chunk_id, score, v_rank, k_rank))
    scored.sort(key=lambda x: -x[1])
    return scored[:top_k]

async def _load_chunks(
    db: AsyncSession,
    fused: list[tuple[int, float, int | None, int | None]]
) -> list[RetrievedChunk]:
    """
    按融合顺序批量加载完整数据
    根据 RRF 融合结果加载完整 Chunk(带 document),保持 RRF 顺序。
    """

    if not fused:
        return []
    chunk_ids = [f[0] for f in fused]
    stmt = (
        select(Chunk)
        .options(selectinload(Chunk.document))
        .where(Chunk.id.in_(chunk_ids))
    )
    result = await db.execute(stmt)
    chunks_by_id = {
        c.id: c for c in result.scalars().all()
    }

    retrieved = []
    for chunk_id, score, v_rank, k_rank, in fused:
        chunk = chunks_by_id.get(chunk_id)
        if chunk is None:
            continue
        retrieved.append(
            RetrievedChunk(
                chunk=chunk,
                document=chunk.document,
                score=score,
                vector_rank=v_rank,
                keyword_rank=k_rank
            )
        )
    return retrieved

async def _hybrid_retrieve(
    db: AsyncSession,
    question: str,
    query_vector: list[float],
    candidates: int,
) -> list[RetrievedChunk]:
    """向量 + 关键词并行检索,RRF 融合,返回 top_k 结果。"""
    per_path = candidates * CANDIDATES_MULTIPLIER

    vector_rankings = await _retrieve_by_vector(db, query_vector, per_path)
    keyword_rankings = await _retrieve_by_keyword(db, question, per_path)

    logger.info(
        "hybrid candidates: vector=%d, keyword=%d, overlap=%d",
        len(vector_rankings),
        len(keyword_rankings),
        len(set(vector_rankings) & set(keyword_rankings)),
    )

    fused = await _rrf_fuse(vector_rankings, keyword_rankings, candidates)

    return await _load_chunks(db, fused)

async def _rerank_chunks(
    question: str,
    candidates: list[RetrievedChunk],
    top_k: int
) -> list[RetrievedChunk]:
    """对 candidates 做 cross-encoder rerank,返回 top_k。"""
    if not candidates:
        return []

    # 走 SiliconFlow /v1/rerank(异步网络调用,直接 await)
    docs = [rc.chunk.content for rc in candidates]
    scores = await do_rerank(question, docs)

    # 用 rerank 分数排序
    for rc, score in zip(candidates, scores):
        rc.rerank_score = score
        metrics.RERANK_SCORE.observe(float(score))

    reranked = sorted(candidates, key = lambda rc: rc.rerank_score or 0.0, reverse=True)
    return reranked[:top_k]

# ---------- 内部:Prompt 组装 ----------
def _format_context(retrieved: list[RetrievedChunk]) -> str:
    parts = []
    for i, rc in enumerate(retrieved, start=1):
        parts.append(f"[{i}] {rc.chunk.content}")
    return "\n\n".join(parts)

# ---------- 内部:生成 ----------
def _build_user_prompt(question: str, context: str, recent_messages: list[Message]) -> str:
    user_prompt = USER_PROMPT_TEMPLATE.format(context=context, question=question)
    # 历史记录
    if recent_messages:
        history = "\n".join([f"{m.role}:{m.content}" for m in recent_messages])
        history = re.sub(r"\[\d+\]", "", history) # 清除历史记录中的引用符号，避免影响提示词
        history_prompt = HISTORY_PROMPT_TEMPLATE.format(history=history)
        user_prompt = history_prompt + user_prompt
    return user_prompt

def _record_token_usage(usage) -> None:
    """委托给 metrics.record_usage(现在同时记 token + 成本)。usage 可能为 None。"""
    metrics.record_usage(settings.chat_model, usage)


async def _generate_answer(question: str, context: str, recent_messages: list[Message], system_prompt: str | None = None) -> str:
    client = get_openai_client()

    response = await client.chat.completions.create(
        model=settings.chat_model,
        messages=[
            {"role": "system", "content": system_prompt or SYSTEM_PROMPT},
            {"role": "user", "content": _build_user_prompt(question, context, recent_messages)},
        ],
        temperature=0.1,
        max_tokens=1024,
        # Qwen3.5 是思考模型,RAG 答案生成不需要思考链(否则 token 全耗在 reasoning 上、content 为空)
        extra_body={"enable_thinking": False},
    )
    _record_token_usage(response.usage)

    content = response.choices[0].message.content
    if not content:
        raise RuntimeError("LLM returned empty response")

    return content.strip()

async def _generate_answer_stream(question: str, context: str, recent_messages: list[Message]) -> AsyncGenerator[str]:
    """流式版 _generate_answer:逐个 yield token 文本,不等整段生成完。"""

    client = get_openai_client()

    stream = await client.chat.completions.create(
        model=settings.chat_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _build_user_prompt(question, context, recent_messages)},
        ],
        temperature=0.1,
        max_tokens=1024,
        stream=True,
        stream_options={"include_usage": True},  # 让最后一帧带 token 用量
        extra_body={"enable_thinking": False},   # Qwen3.5 思考模型,生成不需要思考链
    )

    async for chunk in stream:
        # 尾帧/usage 帧 choices 为空:这里顺便把 token 用量记进指标
        if not chunk.choices:
            _record_token_usage(chunk.usage)
            continue

        delta = chunk.choices[0].delta.content
        if delta:
            yield delta

# ---------- 对外 API ----------
async def retrieve(
    db: AsyncSession,
    *,
    search_query: str,
    top_k: int = DEFAULT_TOP_K
) -> list[RetrievedChunk]:
    """只检索不生成。流式链路用它拿 sources;query() 也复用它。"""
    # 1. 把 question embed 成向量
    query_vector = await embed_query(search_query)

    # Each path returns a broader candidate set before RRF fusion.
    candidates = await _hybrid_retrieve(
        db, question=search_query, query_vector=query_vector,
        candidates=RERANK_CANDIDATES
    )
    metrics.RETRIEVAL_CANDIDATES.observe(len(candidates))

    if not candidates:
        return []

    # Rerank
    if ENABLE_RERANK:
        return await _rerank_chunks(search_query, candidates, top_k)
    else:
        return candidates[:top_k]

async def generate_stream(
    question: str,
    retrieved: list[RetrievedChunk],
    recent_messages: list[Message],
):
    """对已检索到的 chunks 流式生成答案,逐 token yield。"""
    context = _format_context(retrieved)
    async for token in _generate_answer_stream(question, context, recent_messages):
        yield token

async def query(
    db: AsyncSession,
    *,
    question: str,
    search_query: str,
    recent_messages: list[Message],
    top_k: int = DEFAULT_TOP_K,
    system_prompt: str | None = None,
) -> QueryResult:
    """
    完整的 RAG 查询流程。

    Args:
        db: 数据库 session
        question: 用户问题
        top_k: 检索返回的 chunk 数量

    Returns:
        答案 + 引用源
    """
    logger.info("query: %s / search_query: %s (top_k=%d)", question, search_query, top_k)

    retrieved = await retrieve(db, search_query=search_query, top_k=top_k)
    if not retrieved:
        return QueryResult(answer=NO_CONTEXT_ANSWER, sources=[])

    for i, rc in enumerate(retrieved, start=1):
        logger.debug(
            "  [%d] rrf=%.4f rerank=%s v=%s k=%s doc=%s chunk=%d",
            i, rc.score,
            f"{rc.rerank_score:.4f}" if rc.rerank_score else "N/A",
            rc.vector_rank, rc.keyword_rank,
            rc.document.filename, rc.chunk.chunk_index,
        )

    # 3. 组装 context(把多个 chunk 用分隔符拼接)
    content = _format_context(retrieved)
    logger.info(content)

    # 4. 调 LLM 生成答案
    answer = await _generate_answer(question, content, recent_messages, system_prompt)
    return QueryResult(answer=answer, sources=retrieved)
