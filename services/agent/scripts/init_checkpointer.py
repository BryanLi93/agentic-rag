"""启动 Agent 前执行：python -m scripts.init_checkpointer。"""

import asyncio

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from app.config import settings


async def main() -> None:
    async with AsyncPostgresSaver.from_conn_string(settings.checkpoint_conninfo) as checkpointer:
        await checkpointer.setup()
    print("Agent checkpoint tables initialized.")


if __name__ == "__main__":
    asyncio.run(main())
