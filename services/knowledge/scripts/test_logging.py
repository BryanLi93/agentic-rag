"""
手动验证 structlog 与标准库 logging 的桥接效果。

一次运行就能看出前后对比:
  - 桥接前:第三方库(走标准库 logging)的日志,要么裸文本、要么直接丢失
  - 桥接后:同样的日志被并进同一条管道,结构化、格式统一

跑法(JSON 输出,对比最清晰):
    LOG_JSON=true python -m scripts.test_logging
"""
import logging

import structlog

# ---------- 桥接前:还没调用 configure_logging(),即标准库 logging 的默认状态 ----------
# 等价于 1a 对第三方库的处理:structlog 没接管 stdlib,uvicorn 之外的库日志放任自流。
print("\n########## 桥接前(标准库 logging 未被接管)##########", flush=True)
logging.getLogger("sqlalchemy.engine").info("BEGIN (implicit)")     # INFO:被默认 level=WARNING 拦掉 -> 整条丢失
logging.getLogger("openai").warning("retrying request attempt=2")   # WARNING:裸文本输出,没有时间/级别/来源

# ---------- 桥接后:configure_logging() 把标准库 logging 接到同一条管道 ----------
from app.logging_config import configure_logging

configure_logging()
print("\n########## 桥接后(标准库 logging 并入同一管道)##########", flush=True)
logging.getLogger("sqlalchemy.engine").info("BEGIN (implicit)")     # 现在出现了,而且结构化
logging.getLogger("openai").warning("retrying request attempt=2")   # 结构化
structlog.get_logger().info("our_app_log", candidates=20)           # 我们自己的日志,同一种格式
