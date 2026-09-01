import asyncio
import logging
import httpx
import hashlib

from openai import APIError
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
)

from app.config import settings
from app.llm import get_openai_client
from app.cache import cache_get_json, cache_set_json

logger = logging.getLogger(__name__)

# ---------- 常量 ----------

# 单次请求最多 32 条文本(SiliconFlow embeddings 硬上限就是 32 条/请求)
BATCH_SIZE = 32

# 批之间主动节流。SiliconFlow 限流比 Gemini free tier 宽松,给 0.5 秒留点余量即可;
# 撞限流主要靠下面的 tenacity 退避兜底,不靠这里硬等。
THROTTLE_SECONDS = 0.5

# ---------- 内部:单次 API 调用(带重试) ----------

async def _embed_batch_once(texts: list[str]) -> list[list[float]]:
    client = get_openai_client()

    resp = await client.embeddings.create(
        model=settings.embedding_model,
        input=texts,
        # bge-m3 固定输出 1024 维;SiliconFlow 的 dimensions 参数只对 Qwen3 系列生效,这里不传
    )
    # OpenAI 按 index 返回,排序确保和输入顺序一一对应
    data = sorted(resp.data, key=lambda d: d.index)
    return [d.embedding for d in data]

async def _embed_batch_with_retry(texts: list[str]) -> list[list[float]]:
    """带 tenacity 重试的批量 embedding。"""
    async for attempt in AsyncRetrying(
        stop=stop_after_attempt(6),
        wait=wait_exponential(multiplier=2, min=4, max=60),
        retry=retry_if_exception_type((APIError, httpx.HTTPError)),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    ):
        with attempt:
            return await _embed_batch_once(texts)
    # tenacity 保证 reraise=True 时这里不会被执行
    raise RuntimeError("unreachable")

def _embed_cache_key(text: str) -> str:
    h  = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return f"emb:{settings.embedding_model}:{settings.embedding_dim}:{h}"

# ---------- 对外接口 ----------

async def embed_documents(texts: list[str]) -> list[list[float]]:
    """
    文档入库时调用。会自动:
    - 按 BATCH_SIZE 切批
    - 批之间主动节流(避免撞 RPM 上限)
    - 失败重试

    返回与输入顺序一一对应的 embedding 列表。
    """
    if not texts:
        return []

    all_embeddings: list[list[float]] = []
    total_batches = (len(texts) + BATCH_SIZE - 1) // BATCH_SIZE

    for i in range(0, len(texts), BATCH_SIZE):
        batch_idx = i // BATCH_SIZE + 1
        batch = texts[i : i + BATCH_SIZE]
        logger.info(
            "embedding batch %d/%d (size=%d)", batch_idx, total_batches, len(batch)
        )

        embeddings = await _embed_batch_with_retry(batch)
        all_embeddings.extend(embeddings)

        # 主动节流(最后一批不用等)
        if batch_idx < total_batches:
            await asyncio.sleep(THROTTLE_SECONDS)

    return all_embeddings


async def embed_query(text: str) -> list[float]:
    """
    用户查询时调用。单条调用(OpenAI 无 task_type,query 和 document 同一模型)。
    """
    cache_key = _embed_cache_key(text)
    cache = await cache_get_json(cache_key)
    if cache is not None:
        return cache

    embeddings = (await _embed_batch_with_retry([text]))[0]
    await cache_set_json(cache_key, embeddings, 60*60*24*7)
    return embeddings
