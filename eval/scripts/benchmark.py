"""性能面板:记录每题 latency / tokens / cost,并与质量分合并。

质量分(03)只说"答得好不好",这步补"答得多快、多贵":
- latency: 客户端测 /query 的墙钟时间(最直接)
- tokens : 抓 RAG 的 /metrics(rag_llm_tokens_total 全局计数器)前后差值
- cost   : tokens × 单价(RAG 的单价是占位 0,这里在评测侧用真实单价算)

前置:RAG 服务在 8000;ans:* 答案缓存为空(命中缓存会让 token=0、延迟失真)。
"""
import json
import os
import re
import time
import statistics as st
from pathlib import Path

import httpx
import pandas as pd
from dotenv import load_dotenv

load_dotenv()
RAG = os.getenv("RAG_API_BASE", "http://127.0.0.1:8000").rstrip("/")
ROOT = Path(__file__).resolve().parent.parent
GOLDEN = json.loads((ROOT / "data" / "golden.json").read_text(encoding="utf-8"))["items"]
REPORTS = ROOT / "reports"

MODEL = "Qwen/Qwen3.5-9B"
# 硅基流动 Qwen3.5-9B 真实单价(元 / 1K tokens, 输入 <128k 档)
PRICE = {"prompt": 0.0005, "completion": 0.004}


def read_tokens() -> tuple[int, int]:
    """从 /metrics 读累计 (prompt, completion) token。"""
    text = httpx.get(f"{RAG}/metrics", timeout=30).text

    def grab(kind: str) -> int:
        m = re.search(
            rf'rag_llm_tokens_total\{{model="{re.escape(MODEL)}",type="{kind}"\}}\s+([\d.]+)',
            text,
        )
        return int(float(m.group(1))) if m else 0

    return grab("prompt"), grab("completion")


# ---- 逐题测量 ----
rows = []
for it in GOLDEN:
    p0, c0 = read_tokens()
    t0 = time.perf_counter()
    r = httpx.post(f"{RAG}/query", json={"question": it["question"], "top_k": 3}, timeout=120)
    r.raise_for_status()
    latency_ms = round((time.perf_counter() - t0) * 1000)
    p1, c1 = read_tokens()
    prompt_tok, completion_tok = p1 - p0, c1 - c0
    cost = prompt_tok / 1000 * PRICE["prompt"] + completion_tok / 1000 * PRICE["completion"]
    rows.append({
        "id": it["id"],
        "latency_ms": latency_ms,
        "prompt_tokens": prompt_tok,
        "completion_tokens": completion_tok,
        "cost_yuan": round(cost, 6),
    })
    print(f"{it['id']:<28} {latency_ms:6d}ms  prompt={prompt_tok:5d} completion={completion_tok:4d}")

perf = pd.DataFrame(rows)

# ---- 和质量分合并成统一面板 ----
qual = pd.read_csv(REPORTS / "report.csv")[
    ["id", "faithfulness", "answer_relevancy", "context_recall",
     "llm_context_precision_with_reference"]
].rename(columns={"llm_context_precision_with_reference": "precision"})
panel = qual.merge(perf, on="id", how="outer")
panel.to_csv(REPORTS / "panel.csv", index=False)

# ---- 运营汇总 ----
lat = perf["latency_ms"].tolist()
summary = {
    "n": len(perf),
    "latency_avg_ms": round(st.mean(lat)),
    "latency_max_ms": max(lat),
    "tokens_total": int(perf[["prompt_tokens", "completion_tokens"]].sum().sum()),
    "cost_total_yuan": round(perf["cost_yuan"].sum(), 6),
}
(REPORTS / "perf_summary.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
)

print("\n===== 统一面板(质量 + 运营) =====")
print(panel.to_string(index=False))
print("\n===== 运营汇总 =====")
print(json.dumps(summary, ensure_ascii=False, indent=2))
