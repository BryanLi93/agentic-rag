import json
import logging
from typing import Any

import redis.asyncio as redis
from redis.exceptions import RedisError

from app.config import settings

logger = logging.getLogger(__name__)

_redis: redis.Redis | None = None

def get_redis() -> redis.Redis:
    global _redis
    if _redis is None:
        _redis = redis.from_url(
            settings.redis_url,
            decode_responses=True
        )
    return _redis

async def cache_get_json(key: str) -> Any | None:
    """读缓存。任何 Redis 故障都降级成'未命中'(返回 None),绝不拖垮主流程。"""
    try:
        raw = await get_redis().get(key)
    except RedisError as e:
        logger.warning("cache get failed key=%s err=%s", key, e)
        return None

    return json.loads(raw) if raw is not None else None

async def cache_set_json(key: str, value: Any, ttl: int) -> None:
    """写缓存。失败只记日志,不抛。"""
    try:
        await get_redis().set(key, json.dumps(value), ex=ttl)
    except RedisError as e:
        logger.warning("cache set failed key=%s err=%s", key, e)