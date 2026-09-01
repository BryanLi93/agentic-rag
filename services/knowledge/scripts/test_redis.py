import asyncio
from app.cache import get_redis

async def main():
    r = get_redis()
    print("ping:", await r.ping())        # True
    await r.set("hello", "world")
    print("get:", await r.get("hello"))   # world

asyncio.run(main())