"""显式启用 AGENT_POSTGRES_TEST=1 才连接数据库；只读写独立随机 schema。"""

import json
import os
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4

import httpx
from psycopg import AsyncConnection, sql
from psycopg.conninfo import make_conninfo
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from test_conversations import ToolCompatibleFakeModel
from app.agent import agent_runtime, get_agent
from app.config import settings
from app.streaming import stream_agent_events
from scripts.init_checkpointer import main as init_checkpointer


@unittest.skipUnless(os.environ.get("AGENT_POSTGRES_TEST") == "1", "需显式启用 PostgreSQL 集成测试")
class PostgresPersistenceTests(unittest.IsolatedAsyncioTestCase):
    async def test_reconnect_restores_messages_and_tool_artifact(self) -> None:
        schema = "agent_test_" + uuid4().hex
        conninfo = settings.checkpoint_conninfo
        async with await AsyncConnection.connect(conninfo, autocommit=True) as admin:
            await admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
            try:
                scoped = make_conninfo(conninfo, options=f"-c search_path={schema}")
                with patch("scripts.init_checkpointer.settings", SimpleNamespace(checkpoint_conninfo=scoped)):
                    await init_checkpointer()
                    await init_checkpointer()  # 可重复执行，随后运行阶段不再建表。
                source = {
                    "id": 1, "chunk_id": 42, "document_id": 7,
                    "document_filename": "test-rag.md", "chunk_index": 0,
                    "content": "RRF 按排名融合。", "similarity": 0.8,
                    "vector_rank": 1, "keyword_rank": None, "rerank_score": None,
                }
                first_model = ToolCompatibleFakeModel(responses=[
                    AIMessage(content="", tool_calls=[{
                        "id": "test-call", "name": "search_knowledge_base",
                        "args": {"query": "RRF"},
                    }]),
                    AIMessage(content="RRF 按排名融合。[1]"),
                ])
                client = httpx.AsyncClient(base_url="http://knowledge.test", transport=httpx.MockTransport(
                    lambda request: httpx.Response(200, json={"sources": [source]}),
                ))
                with patch("app.agent.settings", SimpleNamespace(checkpoint_conninfo=scoped)):
                    with patch("app.agent.get_chat_client", return_value=first_model), patch(
                        "app.tools.knowledge_base.httpx.AsyncClient", return_value=client,
                    ):
                        async with agent_runtime():
                            frames = [json.loads(f[6:]) async for f in stream_agent_events("我在学 RRF")]
                            thread_id = frames[-1]["thread_id"]
                            self.assertEqual(next(f for f in frames if f["type"] == "sources")["sources"], [source])
                    with self.assertRaises(RuntimeError):
                        get_agent()

                    # 连接池、Saver、Agent 全部重新创建，历史必须来自数据库。
                    second_model = ToolCompatibleFakeModel(responses=[AIMessage(content="它按排名融合。")])
                    with patch("app.agent.get_chat_client", return_value=second_model):
                        async with agent_runtime():
                            frames = [json.loads(f[6:]) async for f in stream_agent_events("它怎么融合？", thread_id)]
                            self.assertEqual(frames[-1]["thread_id"], thread_id)
                            state = await get_agent().aget_state({"configurable": {"thread_id": thread_id}})
                            messages = state.values["messages"]
                            self.assertEqual([m.content for m in messages if isinstance(m, HumanMessage)], ["我在学 RRF", "它怎么融合？"])
                            result = next(m for m in messages if isinstance(m, ToolMessage))
                            self.assertEqual(result.artifact, {"sources": [source]})
                            isolated = await get_agent().aget_state({"configurable": {"thread_id": "other-thread"}})
                            self.assertFalse(isolated.values)
            finally:
                # 只删除本测试刚创建的随机 schema，不操作 public 或业务文档表。
                await admin.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
