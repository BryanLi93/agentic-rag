"""
Rerank 层:调用硅基流动(SiliconFlow)的 /v1/rerank 对召回候选做精排。

模型 BAAI/bge-reranker-v2-m3 不再本地推理,改走 SiliconFlow 的 rerank 接口
——它不是 OpenAI SDK 的方法,得用 httpx 裸调。和 chat/embedding 共用同一个
base_url + key(见 config)。
"""
from __future__ import annotations

import logging
from typing import Sequence

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# base_url 已经是 .../v1,拼上 /rerank 就是完整端点
_RERANK_URL = settings.openai_base_url.rstrip("/") + "/rerank"
_TIMEOUT = httpx.Timeout(30.0)


async def rerank(query: str, documents: Sequence[str]) -> list[float]:
    """
    对一组候选文档按相关性打分(走 SiliconFlow /v1/rerank)。

    Args:
        query: 用户问题
        documents: 候选 chunks 的文本列表

    Returns:
        和 documents 等长、按输入顺序对齐的相关性分数列表(0-1,越大越相关)。
        API 按分数降序返回 {index, relevance_score},这里按 index 回填到原顺序;
        裁剪 top_k 交给调用方(retrieval._rerank_chunks),所以这里不传 top_n。
    """
    if not documents:
        return []

    payload = {
        "model": settings.rerank_model,
        "query": query,
        "documents": list(documents),
        "return_documents": False,
    }
    headers = {"Authorization": f"Bearer {settings.openai_api_key}"}

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(_RERANK_URL, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    # 按输入顺序对齐:先全填 0,再按 result.index 回填实际分数
    scores = [0.0] * len(documents)
    for item in data["results"]:
        scores[item["index"]] = float(item["relevance_score"])
    return scores
