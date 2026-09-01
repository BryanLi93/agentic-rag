"""
对比答案缓存有无的延迟。先起服务:fastapi dev app/main.py
跑:.venv/bin/python -m scripts.bench_cache
"""
import asyncio
import time

import httpx

from app.cache import get_redis

API = "http://127.0.0.1:8000"
QUESTION = "什么是 RAG?"
TOP_K = 5


async def _post_query() -> float:
    """POST 一次 /query,返回耗时(秒)。"""
    async with httpx.AsyncClient(timeout=60) as client:
        t = time.perf_counter()
        resp = await client.post(
            f"{API}/query",
            json={"question": QUESTION, "top_k": TOP_K},
        )
        resp.raise_for_status()
        return time.perf_counter() - t


async def main():
    redis = get_redis()

    # 1. 清掉答案缓存,保证第一次是真·冷启动(未命中)
    keys = await redis.keys("ans:*")
    if keys:
        await redis.delete(*keys)
    print(f"已清 {len(keys)} 个 ans:* 键\n")

    # 2. 冷:未命中,走完整 检索 + LLM 生成
    cold = await _post_query()
    print(f"无缓存(冷,走 LLM 生成): {cold:.3f}s")

    # 3. 热:命中答案缓存,跳过生成
    warm = await _post_query()
    print(f"有缓存(热,命中):        {warm:.3f}s")

    print(f"\n提速 {cold / warm:.0f}x,每次命中省 {cold - warm:.3f}s")


asyncio.run(main())