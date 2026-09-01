# AgenticRAG 离线评测

对知识服务进行黑盒离线评测。评测代码只依赖 `/query` 和 `/metrics` 接口约定，不导入业务实现。

## 数据流

```text
data/golden.json
    │
    ├── collect.py ───────> data/eval_dataset.json
    │                              │
    │                              └── evaluate.py ──> report.csv + summary.json
    │
    ├── benchmark.py ─────> panel.csv + perf_summary.json
    │
    └── compare_prompts.py <version> ──> prompt_runs.json
```

四项质量指标：

- `faithfulness`：回答是否被检索上下文支持。
- `answer_relevancy`：回答是否切题。
- `context_recall`：参考答案所需信息是否被召回。
- `context_precision`：召回片段中相关内容是否靠前且占比合理。

## 运行

从仓库根目录执行；模型服务配置读取根目录 `.env`。

```bash
eval/.venv/bin/python eval/scripts/smoke_score.py
eval/.venv/bin/python eval/scripts/collect.py
eval/.venv/bin/python eval/scripts/evaluate.py
eval/.venv/bin/python eval/scripts/benchmark.py
eval/.venv/bin/python eval/scripts/compare_prompts.py v1
```

运行 `collect.py`、`benchmark.py` 和 `compare_prompts.py` 前，需要先启动知识服务并导入对应测试文档。运行 `benchmark.py` 前应清空答案缓存，避免 Token 用量与延迟结果失真。
