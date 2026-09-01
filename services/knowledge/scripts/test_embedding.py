"""验证 embedding 模块。运行:python -m scripts.test_embedding"""
import asyncio
import logging

from app.embedding import embed_documents, embed_query
from app.config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


async def main():
    print(f"Model: {settings.embedding_model}")
    print(f"Dim:   {settings.embedding_dim}\n")

    # 测试 1:文档批量 embedding
    docs = [
        "Python 是一种解释型编程语言",
        "FastAPI 是一个现代的 Python web 框架",
        "向量数据库用于存储 embedding",
    ]
    print("Embedding documents...")
    doc_embeddings = await embed_documents(docs)
    assert len(doc_embeddings) == len(docs), "返回数量不匹配"
    assert len(doc_embeddings[0]) == settings.embedding_dim, (
        f"维度不对,期望 {settings.embedding_dim},实际 {len(doc_embeddings[0])}"
    )
    print(f"OK: {len(doc_embeddings)} docs, dim={len(doc_embeddings[0])}\n")

    # 测试 2:query embedding
    print("Embedding query...")
    query = "什么是 web 框架?"
    query_embedding = await embed_query(query)
    assert len(query_embedding) == settings.embedding_dim
    print(f"OK: dim={len(query_embedding)}\n")

    # 测试 3:简单相似度验证(余弦距离)
    import math

    def cosine(a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        return dot / (norm_a * norm_b)

    print("Similarity scores (query vs each doc):")
    for doc, emb in zip(docs, doc_embeddings):
        sim = cosine(query_embedding, emb)
        print(f"  {sim:.4f}  {doc}")
    print("\n预期:第 2 句(FastAPI 是 web 框架)应该相似度最高")


if __name__ == "__main__":
    asyncio.run(main())