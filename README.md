# AgenticRAG

**全栈 Agentic RAG 知识助手** — 基于混合检索、引用溯源、LangGraph Agent、SSE 流式输出与离线评测构建。

## 核心能力

- **知识服务**：文件入库、向量检索与全文检索的混合召回、RRF、可选 Rerank、多轮问题改写与结构化引用。
- **Agent 服务**：LangGraph Agent、知识库工具、工具执行轨迹与 Token 级 SSE 输出。
- **Web 应用**：Next.js BFF、RAG / Agent 双链路交互、文档上传、来源面板、停止与重试。
- **离线评测**：黄金测试集（Golden Dataset）、Ragas 四项质量指标、延迟 / Token / 成本统计与 Prompt A/B。
- **可观测性**：Redis 缓存、结构化日志、`trace_id` 与 Prometheus 指标。

## 项目结构

```text
.
├── apps/web/                 # Next.js 产品界面与 BFF
├── services/knowledge/      # FastAPI 知识 / RAG 服务
├── services/agent/          # FastAPI + LangGraph Agent 服务
├── eval/                    # 离线 RAG 评测
├── docs/architecture.md     # 系统架构与接口约定
└── docker-compose.yml       # Web、Agent、Knowledge、PostgreSQL、Redis
```

## 快速启动

运行环境：Docker Desktop。

```bash
cp .env.example .env
# 编辑 .env，填入 OpenAI 兼容接口的 API Key 与模型配置
docker compose up --build
```

服务地址：

- Web：http://127.0.0.1:3000
- 知识服务 API：http://127.0.0.1:8000/docs
- 知识服务健康检查：http://127.0.0.1:8000/health
- Agent 服务 API：http://127.0.0.1:8100/docs

通过 Web 上传 `.txt`、`.md` 或 `.pdf` 文档后，即可体验知识库问答和 Agent 工具调用。

## 本地开发

启动 PostgreSQL 与 Redis：

```bash
docker compose up -d postgres redis
```

知识服务：

```bash
python3.12 -m venv services/knowledge/.venv
services/knowledge/.venv/bin/pip install -r services/knowledge/requirements.txt
PYTHONPATH=services/knowledge services/knowledge/.venv/bin/python -m scripts.init_db
services/knowledge/.venv/bin/uvicorn --app-dir services/knowledge app.main:app --port 8000
```

Agent 服务：

```bash
python3.12 -m venv services/agent/.venv
services/agent/.venv/bin/pip install -r services/agent/requirements.txt
services/agent/.venv/bin/uvicorn --app-dir services/agent app.main:app --port 8100
```

Web：

```bash
npm --prefix apps/web ci
npm --prefix apps/web run dev
```

## 基础检查

```bash
python3 -m compileall -q services/knowledge/app services/agent/app eval/scripts
npm --prefix apps/web run lint
npm --prefix apps/web run build
docker compose config --quiet
```

系统设计、数据流和 SSE 接口约定见 [系统架构](docs/architecture.md)，评测方法见 [离线评测](eval/README.md)。
