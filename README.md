# AgenticRAG

**全栈 Agentic RAG 知识助手** — 基于混合检索、引用溯源、LangGraph Agent、SSE 流式输出与离线评测构建。

## 核心能力

- **知识服务**：文件入库、向量检索与全文检索的混合召回、RRF、可选 Rerank、多轮问题改写与结构化引用。
- **Agent 服务**：LangGraph Agent、知识库工具、工具执行轨迹与 Token 级 SSE 输出，支持基于 PostgreSQL checkpoint 的 API 多轮会话。
- **Web 应用**：统一 Agent 聊天入口、多轮追问、文档上传、引用面板、工具轨迹、停止与重新发送。
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
PYTHONPATH=services/agent services/agent/.venv/bin/python -m scripts.init_checkpointer
services/agent/.venv/bin/uvicorn --app-dir services/agent app.main:app --port 8100
```

Agent 启动需要 PostgreSQL：默认复用 `.env` 的 `DATABASE_URL`，也可用 `AGENT_DATABASE_URL` 指向独立数据库。首次部署或升级 checkpointer 后，先执行 `scripts.init_checkpointer` 创建/迁移表，成功后再启动服务；脚本可重复执行，不修改 Knowledge 文档表。初始化账号需要 DDL 权限，运行阶段不再执行建表。当前使用单 worker，重启不会丢失已写入的会话历史。

Docker Compose 通过一次性 `agent-init` 服务执行初始化，Agent 等待其成功退出后启动。升级部署使用 `docker compose up --build`；单独 `restart agent` 不会执行迁移。不要并发运行多个初始化任务。本地若漏跑脚本，服务可能启动但请求会因缺表失败，运行时不会自动补建。

Web 已统一使用 Agent 并传递会话 ID；也可通过 Agent API 测试两轮：

```bash
curl -N http://127.0.0.1:8100/agent/stream \
  -H 'Content-Type: application/json' \
  -d '{"question":"根据笔记介绍 RRF"}'

# 将上一轮 done 中的 thread_id 填入下方；也可重启 Agent 后再发第二轮。
curl -N http://127.0.0.1:8100/agent/stream \
  -H 'Content-Type: application/json' \
  -d '{"question":"它和 Rerank 有什么区别？","thread_id":"替换为上一轮的ID"}'
```

不传 `thread_id` 会开启新会话。checkpoint 不提供鉴权、历史列表、自动过期或重试幂等，部署边界见 [系统架构](docs/architecture.md)。

Agent 单元测试与可选数据库测试（假模型，不调用外部 LLM）：

```bash
PYTHONPATH=services/agent services/agent/.venv/bin/python -B -m unittest discover -s services/agent/tests -v
# 显式启用：在配置的数据库中创建并清理随机测试 schema，不操作业务文档。
AGENT_POSTGRES_TEST=1 PYTHONPATH=services/agent services/agent/.venv/bin/python -B -m unittest discover -s services/agent/tests -p test_postgres.py -v
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
npm --prefix apps/web test
npm --prefix apps/web run build
docker compose config --quiet
```

系统设计、数据流和 SSE 接口约定见 [系统架构](docs/architecture.md)，评测方法见 [离线评测](eval/README.md)。
