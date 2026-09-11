"""用真实 create_agent/checkpointer 和假模型验证多轮，不发外部请求。"""

import asyncio
import importlib
import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import UUID

from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import SecretStr, ValidationError

with patch.dict(os.environ, {
    "OPENAI_API_KEY": "test-key", "OPENAI_BASE_URL": "http://127.0.0.1:1/v1",
    "CHAT_MODEL": "test-model",
}):
    streaming = importlib.import_module("app.streaming")
    from app.schemas import AgentQuery


class ToolCompatibleFakeModel(FakeMessagesListChatModel):
    def bind_tools(self, tools, *, tool_choice=None, **kwargs):
        return self


class ConversationTests(unittest.IsolatedAsyncioTestCase):
    def make_agent(self):
        model = ToolCompatibleFakeModel(responses=[AIMessage(content="收到1"), AIMessage(content="收到2"), AIMessage(content="收到3")])
        with patch("app.agent.get_chat_client", return_value=model):
            from app.agent import build_agent
            from langgraph.checkpoint.memory import InMemorySaver
            return build_agent(InMemorySaver())

    async def test_real_agent_restores_history_and_isolates_threads(self) -> None:
        graph = self.make_agent()

        async def ask(question: str, thread_id: str | None = None) -> str:
            with patch.object(streaming, "get_agent", return_value=graph):
                frames = [json.loads(f[6:]) async for f in streaming.stream_agent_events(question, thread_id)]
            self.assertEqual(frames[-1]["type"], "done")
            return frames[-1]["thread_id"]

        first_id = await ask("我正在学习 RRF")
        UUID(first_id)
        self.assertEqual(await ask("它与 Rerank 有何区别？", first_id), first_id)
        second_id = await ask("什么是 Agent？")
        self.assertNotEqual(first_id, second_id)
        for thread_id, expected in [
            (first_id, ["我正在学习 RRF", "它与 Rerank 有何区别？"]),
            (second_id, ["什么是 Agent？"]),
        ]:
            state = await graph.aget_state({"configurable": {"thread_id": thread_id}})
            self.assertEqual([m.content for m in state.values["messages"] if isinstance(m, HumanMessage)], expected)
            self.assertEqual(len(state.values["messages"]), len(expected) * 2)

        # 新的 Agent 实例有新的 InMemorySaver，不会恢复旧实例的历史。
        fresh = self.make_agent()
        state = await fresh.aget_state({"configurable": {"thread_id": first_id}})
        self.assertFalse(state.values)

    async def test_concurrent_request_rejected_and_cancellation_releases_thread(self) -> None:
        entered = asyncio.Event()
        wait = asyncio.Event()

        async def blocked_stream(*args, **kwargs):
            entered.set()
            await wait.wait()
            if False:
                yield

        with patch.object(streaming, "get_agent", return_value=SimpleNamespace(astream=blocked_stream)):
            events = streaming.stream_agent_events("第一轮", "busy-thread")
            task = asyncio.create_task(anext(events))
            await entered.wait()
            with self.assertRaises(streaming.ThreadBusyError):
                await anext(streaming.stream_agent_events("第二轮", "busy-thread"))
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            self.assertNotIn("busy-thread", streaming._active_threads)
            wait.set()
            frames = [json.loads(f[6:]) async for f in streaming.stream_agent_events("重试", "busy-thread")]
            self.assertEqual(frames[-1], {"type": "done", "thread_id": "busy-thread"})

    async def test_error_releases_thread(self) -> None:
        async def failed_stream(*args, **kwargs):
            raise RuntimeError("模拟模型错误")
            yield

        with patch.object(streaming, "get_agent", return_value=SimpleNamespace(astream=failed_stream)):
            with self.assertRaises(RuntimeError):
                await anext(streaming.stream_agent_events("问题", "failed-thread"))
        self.assertNotIn("failed-thread", streaming._active_threads)

    async def test_close_after_first_frame_waits_for_upstream_before_unlock(self) -> None:
        from app.main import agent_stream
        from langchain_core.messages import AIMessageChunk

        closing = asyncio.Event()
        allow_close = asyncio.Event()
        closed = False

        async def upstream(*args, **kwargs):
            nonlocal closed
            try:
                yield "messages", (AIMessageChunk(content="第一段"), {})
                await asyncio.Event().wait()
            finally:
                closing.set()
                await allow_close.wait()
                closed = True

        # 保留底层流的引用，确保清理来自显式 aclose，而不是垃圾回收。
        agent_events = upstream()
        fake_agent = SimpleNamespace(astream=lambda *args, **kwargs: agent_events)
        with patch.object(streaming, "get_agent", return_value=fake_agent):
            response = await agent_stream(AgentQuery(question="问题", thread_id="close-thread"))
            events = response.body_iterator
            await anext(events)
            close_task = asyncio.create_task(events.aclose())
            try:
                await asyncio.wait_for(closing.wait(), timeout=1)
                self.assertFalse(closed)
                self.assertIn("close-thread", streaming._active_threads)
                with self.assertRaises(streaming.ThreadBusyError):
                    await anext(streaming.stream_agent_events("追问", "close-thread"))
            finally:
                allow_close.set()
                await close_task
                await agent_events.aclose()
        self.assertTrue(closed)
        self.assertNotIn("close-thread", streaming._active_threads)

    async def test_upstream_close_failure_still_releases_thread(self) -> None:
        from langchain_core.messages import AIMessageChunk

        async def upstream(*args, **kwargs):
            try:
                yield "messages", (AIMessageChunk(content="第一段"), {})
            finally:
                raise RuntimeError("close failed")

        with patch.object(streaming, "get_agent", return_value=SimpleNamespace(astream=upstream)):
            events = streaming.stream_agent_events("问题", "close-error-thread")
            await anext(events)
            with self.assertRaisesRegex(RuntimeError, "close failed"):
                await events.aclose()
        self.assertNotIn("close-error-thread", streaming._active_threads)

    async def test_router_passes_thread_id(self) -> None:
        from app.main import agent_stream

        async def event_stream(question, thread_id):
            self.assertEqual((question, thread_id), ("追问", "existing-thread"))
            yield streaming.encode_sse({"type": "done", "thread_id": thread_id})

        with patch("app.main.stream_agent_events", side_effect=event_stream):
            response = await agent_stream(AgentQuery(question="追问", thread_id="existing-thread"))
            frames = [json.loads(f[6:]) async for f in response.body_iterator]
        self.assertEqual(frames, [{"type": "done", "thread_id": "existing-thread"}])

    def test_thread_id_validation_and_old_request_compatibility(self) -> None:
        self.assertIsNone(AgentQuery(question="问题").thread_id)
        for invalid in ["", " ", "a/b", "x" * 129, 123]:
            with self.subTest(thread_id=invalid), self.assertRaises(ValidationError):
                AgentQuery(question="问题", thread_id=invalid)

    async def test_database_connection_failure_closes_pool_and_blocks_agent(self) -> None:
        runtime = importlib.import_module("app.agent")
        pool = AsyncMock()
        pool.__aenter__.return_value = pool
        pool.wait.side_effect = RuntimeError("connection failed")
        with patch.object(runtime, "settings", SimpleNamespace(checkpoint_conninfo="postgresql://test")), patch.object(
            runtime, "AsyncConnectionPool", return_value=pool,
        ):
            with self.assertRaisesRegex(RuntimeError, "connection failed"):
                async with runtime.agent_runtime():
                    self.fail("启动失败时不应接收请求")
        pool.__aexit__.assert_awaited_once()
        with self.assertRaises(RuntimeError):
            runtime.get_agent()

    async def test_runtime_does_not_initialize_tables(self) -> None:
        runtime = importlib.import_module("app.agent")
        pool = AsyncMock()
        pool.__aenter__.return_value = pool
        saver = SimpleNamespace(setup=AsyncMock())
        graph = self.make_agent()
        with patch.object(runtime, "settings", SimpleNamespace(checkpoint_conninfo="postgresql://test")), patch.object(
            runtime, "AsyncConnectionPool", return_value=pool,
        ), patch.object(runtime, "AsyncPostgresSaver", return_value=saver), patch.object(
            runtime, "build_agent", return_value=graph,
        ):
            async with runtime.agent_runtime():
                self.assertIs(runtime.get_agent(), graph)
        saver.setup.assert_not_awaited()
        pool.__aexit__.assert_awaited_once()

    async def test_init_script_runs_setup_and_propagates_failure(self) -> None:
        init = importlib.import_module("scripts.init_checkpointer")
        for failure in [None, RuntimeError("migration failed")]:
            context = AsyncMock()
            saver = context.__aenter__.return_value
            saver.setup.side_effect = failure
            with patch.object(init, "settings", SimpleNamespace(checkpoint_conninfo="postgresql://test")), patch.object(
                init.AsyncPostgresSaver, "from_conn_string", return_value=context,
            ):
                if failure:
                    with self.assertRaisesRegex(RuntimeError, "migration failed"):
                        await init.main()
                else:
                    await init.main()
            saver.setup.assert_awaited_once()
            context.__aexit__.assert_awaited_once()

    def test_database_config_precedence_and_missing_config(self) -> None:
        from app.config import settings

        config = settings.model_copy(update={
            "agent_database_url": None,
            "database_url": SecretStr("postgresql+psycopg://example/db"),
        })
        self.assertEqual(config.checkpoint_conninfo, "postgresql://example/db")
        config.agent_database_url = SecretStr("postgresql://example/agent")
        self.assertEqual(config.checkpoint_conninfo, "postgresql://example/agent")
        config.agent_database_url = None
        config.database_url = None
        with self.assertRaises(ValueError):
            _ = config.checkpoint_conninfo
