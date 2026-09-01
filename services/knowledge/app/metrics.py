"""
Prometheus 指标定义。

集中在这里定义指标对象,业务代码 import 后调用 .inc() / .observe()。
/metrics 端点由 main.py 用 prometheus_client.make_asgi_app() 挂载,
Prometheus 走拉取(pull)模型定时来抓这个端点。

三种类型对照:
  - Counter   只增不减的累加器(QPS 由 rate(counter) 查询时算出,不直接存)
  - Histogram 分桶统计,用来估算 p50/p95/p99 这类分位数
  - Gauge     可上可下的瞬时值(本项目暂未用到)
"""
from __future__ import annotations

from prometheus_client import Counter, Histogram

# ---------- 请求级(在中间件记录)----------
REQUEST_COUNT = Counter(
    "rag_http_requests_total",
    "HTTP 请求总数",
    labelnames=("method", "path", "status"),
)

REQUEST_LATENCY = Histogram(
    "rag_http_request_duration_seconds",
    "HTTP 请求耗时(秒)",
    labelnames=("method", "path"),
    # 默认桶偏 web 短请求;RAG 带 LLM 生成会到几秒,补几个大桶
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30),
)

# ---------- 业务级(在 service 记录)----------
LLM_TOKENS = Counter(
    "rag_llm_tokens_total",
    "LLM token 消耗累计",
    labelnames=("model", "type"),   # type = prompt / completion
)

RETRIEVAL_CANDIDATES = Histogram(
    "rag_retrieval_candidates",
    "每次检索 RRF 融合后的候选 chunk 数",
    buckets=(0, 1, 2, 5, 10, 20, 50),
)

RERANK_SCORE = Histogram(
    "rag_rerank_score",
    "rerank 相关性打分分布",
    buckets=(0, 0.2, 0.4, 0.6, 0.8, 0.9, 1.0),  # SiliconFlow rerank 返回 0-1 归一化分
)

# ---------- 成本（token × 单价）----------
# 单价按每 1K token 配置（单位：元）；单价为 0 的模型只统计 token，不累计成本。
MODEL_PRICES: dict[str, dict[str, float]] = {
    "Qwen/Qwen3.5-9B": {"prompt": 0.0005, "completion": 0.004},   # 硅基流动真实单价(元/1K, 输入<128k 档)
    "Qwen/Qwen3.5-4B": {"prompt": 0.0, "completion": 0.0},
    "BAAI/bge-m3": {"prompt": 0.0, "completion": 0.0},
}

LLM_COST = Counter(
    "rag_llm_cost_total",
    "LLM 调用累计成本(token × 单价,单位见 MODEL_PRICES)",
    labelnames=("model",),
)


def record_usage(model: str, usage) -> None:
    """一次 LLM 调用的 token 用量记进指标,并按单价累加成本。usage 可能为 None。"""
    if not usage:
        return
    prompt = usage.prompt_tokens
    # embedding 的 usage 没有 completion_tokens,用 getattr 兜底防 AttributeError
    completion = getattr(usage, "completion_tokens", 0) or 0
    LLM_TOKENS.labels(model, "prompt").inc(prompt)
    LLM_TOKENS.labels(model, "completion").inc(completion)

    price = MODEL_PRICES.get(model)
    if price:
        cost = prompt / 1000 * price["prompt"] + completion / 1000 * price["completion"]
        LLM_COST.labels(model).inc(cost)
