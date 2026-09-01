import asyncio, time
from app.embedding import embed_query

async def main():
    for label in ("第一次(MISS)", "第二次(HIT)"):
        t = time.perf_counter()
        vec = await embed_query("什么是 RAG?")
        print(f"{label}: {time.perf_counter()-t:.3f}s, dim={len(vec)}")

asyncio.run(main())
