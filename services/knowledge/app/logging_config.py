"""
结构化日志配置:structlog 与标准库 logging 共用一条管道。

相比 1a,这一版多做一件事:把“标准库 logging”也接到同一条 processor 管道上。
于是 uvicorn / sqlalchemy / openai 等第三方库(它们都走标准库 logging)的日志,
也会用同一套字段、同一个渲染器输出 —— 格式统一,将来也能带上同一个 trace_id。

对应讲解:
  - processor 管道                  -> 第 2 节
  - 把标准库 logging 接管过来        -> 第 4 节(本步的主角)
  - dev 彩色 / prod JSON 渲染器切换   -> 第 5 节
"""
from __future__ import annotations

import logging
import sys

import structlog

from app.config import settings


def configure_logging() -> None:
    """配置 structlog + 标准库 logging,让两边日志走同一条管道、同一种渲染。"""

    # 1) 共享 processor:structlog 自己的日志、第三方库的日志,都会经过这几步(往 event_dict 加字段)
    shared_processors = [
        structlog.contextvars.merge_contextvars,      # 把 bind_contextvars 存的字段(第 2 步 trace_id)并进来
        structlog.stdlib.add_logger_name,             # 加 "logger" 字段(如 "uvicorn.access"),好认出日志来源
        structlog.stdlib.add_log_level,               # 加 "level"
        structlog.processors.TimeStamper(fmt="iso"),  # 加 "timestamp"
    ]

    # 2) 末端渲染器:dev 彩色 / prod JSON(由 settings.log_json 切换)
    renderer = (
        structlog.processors.JSONRenderer()
        if settings.log_json
        else structlog.dev.ConsoleRenderer()
    )

    # 3) 配 structlog 自己:走完 shared_processors,最后“交棒”给标准库的 Formatter 去渲染。
    #    末尾不是 renderer,而是 wrap_for_formatter —— 渲染统一交给第 4 步的 formatter 做。
    structlog.configure(
        processors=[
            *shared_processors,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),  # structlog 也通过标准库 logging 输出
        cache_logger_on_first_use=True,
    )

    # 4) 配标准库 logging:用 ProcessorFormatter 当 formatter,统一渲染所有日志
    #    - 来自 structlog 的日志:已过 shared_processors,这里补 StackInfo/exc 后渲染
    #    - 来自第三方库的“外来”日志:用 foreign_pre_chain 补上 shared_processors,再渲染
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,  # 清掉管道内部用的元字段
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()          # 清掉之前(basicConfig 等)装的 handler,避免一条日志打印两遍
    root.addHandler(handler)
    root.setLevel(settings.log_level)

    # 注意:这里特意不去动 uvicorn 自己的 logger。
    # uvicorn 默认给 uvicorn/uvicorn.access 装了自带 handler 且 propagate=False。
    # 之前试图“清 handler + 打开 propagate”把它们也并进管道,结果和 uvicorn 在
    # reloader 下重新配置 logging 的时序打架,导致每条 uvicorn 日志被打印两遍。
    # 取舍:让 uvicorn 用它自己的格式(启动横幅 + access log),我们自己的请求日志
    # 由 trace_id 中间件单独打一条(带 trace_id + 耗时),信息更全,也不重复。
    # sqlalchemy / openai 等普通库无自带 handler,会自动冒泡到上面的 root,无需特殊处理。
