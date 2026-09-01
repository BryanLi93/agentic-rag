"""Prompt A/B:使用指定 prompt 版本采集并评分,再横向比较版本结果。

这是整套评测的"目的":改了 prompt,用数字证明变好还是变差。

用法:
    eval/.venv/bin/python eval/scripts/compare_prompts.py v1
    eval/.venv/bin/python eval/scripts/compare_prompts.py v2

每跑一个版本:
  读 prompts/<版本>.json 的 system_prompt
  → 用它(经 /query 的 system_prompt 覆盖)对全部 golden 题采集答案
  → 4 指标打分(仅知识库内题求均分)
  → 追加进台账 reports/prompt_runs.json(同版本覆盖旧记录)
  → 打印所有版本的对比表

前置:RAG 服务在 8000(已支持 /query 的 system_prompt 覆盖);硅基流动 chat 可用。
"""
import os
import sys
import json
from datetime import datetime
from pathlib import Path

import httpx
import pandas as pd
from dotenv import load_dotenv
from pydantic import SecretStr
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from ragas import SingleTurnSample, EvaluationDataset, evaluate, RunConfig
from ragas.llms import LangchainLLMWrapper
from ragas.embeddings import LangchainEmbeddingsWrapper
from ragas.metrics import (
    Faithfulness, ResponseRelevancy,
    LLMContextRecall, LLMContextPrecisionWithReference,
)

load_dotenv()
ROOT = Path(__file__).resolve().parent.parent
RAG_URL = f"{os.getenv('RAG_API_BASE', 'http://127.0.0.1:8000').rstrip('/')}/query"
GOLDEN = json.loads((ROOT / "data" / "golden.json").read_text(encoding="utf-8"))["items"]
LEDGER = ROOT / "reports" / "prompt_runs.json"

version = sys.argv[1] if len(sys.argv) > 1 else "v1"
cfg = json.loads((ROOT / "prompts" / f"{version}.json").read_text(encoding="utf-8"))
system_prompt = cfg["system_prompt"]

# ---- 裁判 + embeddings ----
judge = LangchainLLMWrapper(ChatOpenAI(
    model=os.environ["CHAT_MODEL"],
    api_key=SecretStr(os.environ["OPENAI_API_KEY"]),
    base_url=os.environ["OPENAI_BASE_URL"],
    extra_body={"enable_thinking": False},
))
emb = LangchainEmbeddingsWrapper(OpenAIEmbeddings(
    model=os.environ["EMBEDDING_MODEL"],
    api_key=SecretStr(os.environ["OPENAI_API_KEY"]),
    base_url=os.environ["OPENAI_BASE_URL"],
    check_embedding_ctx_length=False,
))

# ---- 用该版本 prompt 采集(关键:把 system_prompt 传给 /query 覆盖) ----
samples, in_kbs = [], []
for it in GOLDEN:
    r = httpx.post(RAG_URL, json={
        "question": it["question"], "top_k": 3, "system_prompt": system_prompt,
    }, timeout=120)
    r.raise_for_status()
    data = r.json()
    samples.append(SingleTurnSample(
        user_input=it["question"],
        reference=it["reference"],
        response=data["answer"],
        retrieved_contexts=[s["content"] for s in data["sources"]],
    ))
    in_kbs.append(it.get("in_kb", True))
    print(f"采集[{version}]: {it['id']:<28} {len(data['sources'])} 段")

# ---- 4 指标打分 ----
result = evaluate(
    EvaluationDataset(samples=samples),
    metrics=[Faithfulness(), ResponseRelevancy(),
             LLMContextRecall(), LLMContextPrecisionWithReference()],
    llm=judge, embeddings=emb,
    run_config=RunConfig(max_workers=5, timeout=600),
)
df = result.to_pandas()
df["in_kb"] = in_kbs

# 只取知识库内题求均分(知识库外拒答题会被 ragas 误判 0,不能折进来)
in_kb = df[df["in_kb"]]
scores = {
    "faithfulness": round(in_kb["faithfulness"].mean(), 4),
    "answer_relevancy": round(in_kb["answer_relevancy"].mean(), 4),
    "context_recall": round(in_kb["context_recall"].mean(), 4),
    "context_precision": round(in_kb["llm_context_precision_with_reference"].mean(), 4),
}

# ---- 追加台账(同版本覆盖) ----
ledger = json.loads(LEDGER.read_text(encoding="utf-8")) if LEDGER.exists() else []
ledger = [e for e in ledger if e["version"] != version]
ledger.append({
    "version": version,
    "note": cfg.get("note", ""),
    "time": datetime.now().isoformat(timespec="seconds"),
    **scores,
})
LEDGER.write_text(json.dumps(ledger, ensure_ascii=False, indent=2), encoding="utf-8")

# ---- 对比表 ----
print(f"\n本次[{version}] 均分:", json.dumps(scores, ensure_ascii=False))
print("\n===== 所有版本对比(prompt_runs.json) =====")
cols = ["version", "faithfulness", "answer_relevancy",
        "context_recall", "context_precision", "note"]
print(pd.DataFrame(ledger)[cols].to_string(index=False))
