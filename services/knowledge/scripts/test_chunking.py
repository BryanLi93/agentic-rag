"""验证分块模块。运行:python -m scripts.test_chunking"""
from app.chunking import split_text


def main():
    # 测试 1:中英混合长文本
    text = """
# RAG 系统设计

RAG（Retrieval-Augmented Generation）是一种将检索系统与生成模型结合的架构。
它的核心思想是:在生成答案前,先从知识库中检索相关上下文,再让 LLM 基于上下文回答。

## 核心组件

RAG 系统通常包含以下几个核心组件:

1. 文档解析器 (Document Parser):负责把 PDF、Word、Markdown 等格式的文档转成纯文本。
2. 分块器 (Chunker):把长文本切成适合 embedding 的小段。
3. Embedding 模型:把文本转成高维向量。常见选择有 OpenAI text-embedding-3、Google Gemini Embedding、BGE-M3 等。
4. 向量数据库 (Vector DB):存储 embedding,支持相似度检索。常见有 ChromaDB、pgvector、Pinecone、Milvus 等。
5. Reranker:对初步检索结果二次排序,提升 top-k 质量。

## 检索流程

When a user asks a question, the system first embeds the query into a vector.
Then it searches the vector database for the top-k most similar chunks.
These chunks are concatenated into the prompt as context, along with the original question.
Finally, the LLM generates an answer grounded in the retrieved context.

## 常见问题

- 检索召回不准:可能是 chunk_size 不合适,或者 embedding 模型不擅长当前领域
- 答案产生幻觉:LLM 没严格基于 context,需要在 prompt 里强约束
- 延迟高:embedding API 调用 + 数据库查询 + LLM 生成,每一步都可能成为瓶颈
"""

    chunks = split_text(text=text, chunk_size=200, chunk_overlap=20)

    print(f"原文长度: {len(text)} 字符\n")
    print(f"切出 {len(chunks)} 个 chunks:\n")
    print("=" * 60)

    for chunk in chunks:
        print(f"[Chunk {chunk.index}] ({len(chunk.content)} chars, ~{chunk.token_count} tokens)")
        print(chunk.content)
        print("-" * 60)


if __name__ == "__main__":
    main()