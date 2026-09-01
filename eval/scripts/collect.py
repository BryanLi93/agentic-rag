"""黑盒采集:只保存真实 RAG 输出,不执行质量评分。

读 golden.json → 调真实 RAG /query → 把每条采集结果存成 data/eval_dataset.json。
为什么单独成一步:调 RAG 慢、且每次结果可能不同;采集一次存盘后,
evaluate.py 可以反复跑同一份数据,不必每次都重新请求服务。
前置:RAG 服务起在 8000,且 4 篇文档已入库。
"""
import json
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()
RAG_URL = f"{os.getenv('RAG_API_BASE', 'http://127.0.0.1:8000').rstrip('/')}/query"
DATA = Path(__file__).resolve().parent.parent / "data"
GOLDEN_FILE = DATA / "golden.json"
OUT_FILE = DATA / "eval_dataset.json"

items = json.loads(GOLDEN_FILE.read_text(encoding="utf-8"))["items"]

dataset = []
for it in items:
    resp = httpx.post(
        RAG_URL,
        json={"question": it["question"], "top_k": 3},
        timeout=120,
    )
    resp.raise_for_status()
    data = resp.json()
    dataset.append({
        "id": it["id"],
        "in_kb": it.get("in_kb", True),                              # 知识库外的题标记出来
        "user_input": it["question"],                               # golden
        "reference": it["reference"],                               # golden
        "response": data["answer"],                                 # /query 采集
        "retrieved_contexts": [s["content"] for s in data["sources"]],  # /query 采集
    })
    print(f"采集: {it['id']:<28} 检索到 {len(data['sources'])} 段")

OUT_FILE.write_text(json.dumps(dataset, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\n已存盘: {OUT_FILE.name}  ({len(dataset)} 条)")
