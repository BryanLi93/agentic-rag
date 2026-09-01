"""质量评分与报告生成:读取已存盘的数据,不再请求 RAG 服务。

读 data/eval_dataset.json → 跑 4 个指标 → 存 reports/report.csv(每题)
+ reports/summary.json(汇总) → 打印汇总。

聚合分两套:
- 生成层(faithfulness / answer_relevancy)对全部题求平均;
- 检索层(context_recall / precision)只对"知识库内"的题求平均
  —— 知识库外的题没有可被检索支撑的内容,recall/precision 不具参考意义。
"""
import os
import json
from pathlib import Path

from dotenv import load_dotenv
from pydantic import SecretStr
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from ragas import SingleTurnSample, EvaluationDataset, evaluate, RunConfig
from ragas.llms import LangchainLLMWrapper
from ragas.embeddings import LangchainEmbeddingsWrapper
from ragas.metrics import (
    Faithfulness,
    ResponseRelevancy,
    LLMContextRecall,
    LLMContextPrecisionWithReference,
)

load_dotenv()
ROOT = Path(__file__).resolve().parent.parent
rows = json.loads((ROOT / "data" / "eval_dataset.json").read_text(encoding="utf-8"))
REPORTS = ROOT / "reports"
REPORTS.mkdir(exist_ok=True)

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

samples = [SingleTurnSample(
    user_input=r["user_input"],
    reference=r["reference"],
    response=r["response"],
    retrieved_contexts=r["retrieved_contexts"],
) for r in rows]

result = evaluate(
    EvaluationDataset(samples=samples),
    metrics=[
        Faithfulness(),
        ResponseRelevancy(),
        LLMContextRecall(),
        LLMContextPrecisionWithReference(),
    ],
    llm=judge,
    embeddings=emb,
    run_config=RunConfig(max_workers=3, timeout=600),
)

# ---- 整理 + 存报告 ----
df = result.to_pandas()
df.insert(0, "id", [r["id"] for r in rows])
df.insert(1, "in_kb", [r["in_kb"] for r in rows])
cols = ["faithfulness", "answer_relevancy", "context_recall",
        "llm_context_precision_with_reference"]

df[["id", "in_kb"] + cols].to_csv(REPORTS / "report.csv", index=False)

in_kb = df[df["in_kb"]]
out_kb = df[~df["in_kb"]]
# 4 个指标都只对"知识库内"题求平均:知识库外题是"拒答测试",
# ragas 会给 0(把正确拒答误判成失败),不能折进平均,单独列出人工看。
summary = {
    "n_total": len(df),
    "n_in_kb": int(df["in_kb"].sum()),
    "faithfulness": round(in_kb["faithfulness"].mean(), 4),
    "answer_relevancy": round(in_kb["answer_relevancy"].mean(), 4),
    "context_recall": round(in_kb["context_recall"].mean(), 4),
    "context_precision": round(in_kb["llm_context_precision_with_reference"].mean(), 4),
    "out_of_kb_ids": out_kb["id"].tolist(),  # 需人工确认是否正确拒答
}
(REPORTS / "summary.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

print("\n每题分数:")
print(df[["id", "in_kb"] + cols].to_string(index=False))
print("\n汇总:")
print(json.dumps(summary, ensure_ascii=False, indent=2))
