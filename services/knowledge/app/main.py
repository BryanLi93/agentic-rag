"""AgenticRAG 知识服务主入口。"""
from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.routers import conversation, query, retrieve, upload
from app.config import settings
from app.db import engine
from app.logging_config import configure_logging
from app import metrics


# ---------- 日志 ----------
# 必须在任何 logger 使用前先配好管道
configure_logging()
logger = structlog.get_logger()

# ---------- 生命周期 ----------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动/关闭时的钩子。"""
    logger.info("startup")
    yield
    logger.info("shutdown")
    await engine.dispose()

# ---------- 应用实例 ----------
app = FastAPI(
    title="AgenticRAG 知识服务",
    description="提供文档入库、检索、基于上下文生成与引用溯源。",
    version="0.1.0",
    lifespan=lifespan,
)

# ---------- 中间件:CORS ----------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- 中间件:trace_id + 请求耗时 ----------
@app.middleware("http")
async def trace_context_middleware(request: Request, call_next):
    """给每个请求绑定 trace_id,使本次请求的所有日志自动带上它;
    请求结束打一条 access 日志(method/path/status/耗时)+ 记 Prometheus 指标,并回传 trace_id。"""
    # /metrics 是监控自身的拉取端点,不绑 trace_id、也不计入指标,避免自我污染
    if request.url.path.startswith("/metrics"):
        return await call_next(request)

    trace_id = request.headers.get("X-Trace-Id") or uuid.uuid4().hex[:12]
    structlog.contextvars.bind_contextvars(trace_id=trace_id)
    start = time.perf_counter()
    try:
        response = await call_next(request)
        elapsed = time.perf_counter() - start
        # 用路由模板而非原始 path 当 label,避免 /conversations/{id} 把每个 uuid 撑成一个时间序列
        route = request.scope.get("route")
        path = getattr(route, "path", request.url.path)
        metrics.REQUEST_COUNT.labels(request.method, path, str(response.status_code)).inc()
        metrics.REQUEST_LATENCY.labels(request.method, path).observe(elapsed)
        logger.info(
            "request_completed",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            elapsed_ms=round(elapsed * 1000, 1),
        )
        response.headers["X-Trace-Id"] = trace_id
        return response
    finally:
        # 请求结束清掉,避免 trace_id 残留到下一个复用的协程上下文
        structlog.contextvars.clear_contextvars()

# ---------- 全局异常处理 ----------

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """兜底未捕获异常,避免 stacktrace 泄露给客户端。"""
    trace_id = structlog.contextvars.get_contextvars().get("trace_id")
    logger.exception("unhandled_exception", method=request.method, url=str(request.url))
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": f"服务内部错误：{type(exc).__name__}", "trace_id": trace_id},
    )

# ---------- 路由 ----------
app.include_router(upload.router)
app.include_router(retrieve.router)
app.include_router(query.router)
app.include_router(conversation.router)

@app.get("/")
async def root():
    return {
        "service": "AgenticRAG 知识服务",
        "version": "0.1.0",
        "docs": "/docs",
    }

@app.get("/health")
async def health():
    """健康检查端点(后续 Docker / k8s 健康探针用)。"""
    return {"status": "ok"}

# ---------- 监控指标端点 ----------
# Prometheus 拉取模型:返回当前所有指标的纯文本快照,Prometheus 定时来抓。
# 用普通路由而非 app.mount —— 挂载对不带尾斜杠的 /metrics 会 307 跳到 /metrics/,
# curl 不加 -L 会以为"没反应";普通路由让 GET /metrics 直接 200 返回。
@app.get("/metrics")
async def metrics_endpoint() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
