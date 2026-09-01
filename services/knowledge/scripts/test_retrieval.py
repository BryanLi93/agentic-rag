"""端到端测试 retrieval 服务。需先跑过 test_ingest.py 入库一些数据。"""
import asyncio
import json
import logging
from pathlib import Path

from app.db import AsyncSessionLocal
from app.services.retrieval import query

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

QUESTION_FILE = Path(__file__).resolve().parent / "test_data" / "retrieval_questions.json"


def load_questions() -> list[dict[str, object]]:
    with QUESTION_FILE.open(encoding="utf-8") as f:
        data = json.load(f)
    questions = data["questions"] if isinstance(data, dict) else data
    if not questions:
        raise ValueError(f"no questions found in {QUESTION_FILE}")
    return questions


async def main():
    questions = load_questions()

    async with AsyncSessionLocal() as db:
        for item in questions:
            q = str(item["question"])
            top_k = int(item.get("top_k", 3))
            print("=" * 60)
            print(f"Topic: {item.get('topic', 'general')}")
            print(f"Q: {q}")
            answer = await query(db, question=q, top_k=top_k)
            print(f"A: {answer}")
            print()


if __name__ == "__main__":
    asyncio.run(main())
