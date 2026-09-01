"use client";

import { useCallback, useRef, useState } from "react";
import { parseSSE } from "./sse";
import { createThinkStripper } from "./think";
import type { ChatMessage } from "./types";

export type ChatStatus = "ready" | "streaming" | "error";

/**
 * 每帧如何改写 assistant 草稿;各模式实现见 reducers.ts(ragReduce / agentReduce)。
 * frame 在管道这层是 unknown(后端 JSON 的动态边界),进了具体 reducer 才精确成
 * BackendFrame / AgentFrame —— 调用方按 mode 选定 reducer 时 `as Reduce` 跨这个边界。
 */
export type Reduce = (
  frame: unknown,
  draft: ChatMessage,
  strip: (s: string) => string,
) => void;

/**
 * 基于 fetch + ReadableStream 的最小流式聊天 hook,替代 @ai-sdk/react 的 useChat。
 *
 * 一次发送 = 追加一条 user + 一条空 assistant 草稿 → fetch 后端 SSE →
 * parseSSE 逐帧解出 → reduce 累积进草稿 → 每帧 setMessages 触发重渲染。
 * 请求体固定为 { question, ...extra },extra 由调用方按模式传(如 RAG 的 conversation_id)。
 */
export function useStreamChat({ api, reduce }: { api: string; reduce: Reduce }) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [status, setStatus] = useState<ChatStatus>("ready");
  const [error, setError] = useState<Error | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const messagesRef = useRef<ChatMessage[]>([]); // 让流式回调里能读到最新 messages
  const lastTurn = useRef<{ text: string; body?: Record<string, unknown> } | null>(
    null,
  ); // 供 regenerate 重放

  // 唯一写入口:state 和 ref 一起更新,保证 await 之后的回调读到的是最新值
  const commit = useCallback((next: ChatMessage[]) => {
    messagesRef.current = next;
    setMessages(next);
  }, []);

  // 从 base 起挂一条空 assistant 草稿,消费一条 SSE 流,把每帧累积进草稿
  const stream = useCallback(
    async (text: string, base: ChatMessage[], body?: Record<string, unknown>) => {
      const ac = new AbortController();
      abortRef.current = ac;
      const draft: ChatMessage = {
        id: crypto.randomUUID(),
        role: "assistant",
        text: "",
      };
      commit([...base, draft]);
      setStatus("streaming");
      setError(null);

      const strip = createThinkStripper();
      // 把当前草稿快照写回列表(每帧调一次 → 流式刷新)
      const flush = () =>
        commit(
          messagesRef.current.map((m) => (m.id === draft.id ? { ...draft } : m)),
        );

      try {
        const res = await fetch(api, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ question: text, ...body }),
          signal: ac.signal,
        });
        // 开流前错误(连不上/会话不存在等):route 已把状态码和文案映射好,直接抛
        if (!res.ok || !res.body) {
          throw new Error((await res.text()) || `HTTP ${res.status}`);
        }
        for await (const frame of parseSSE(res.body)) {
          reduce(frame, draft, strip.push);
          flush();
        }
        draft.text += strip.flush(); // <think> 之后可能残留的正文尾巴
        flush();
        setStatus("ready");
      } catch (e) {
        if (ac.signal.aborted) {
          setStatus("ready"); // 用户点了停止:不算错误
          return;
        }
        setError(e instanceof Error ? e : new Error(String(e)));
        setStatus("error");
      }
    },
    [api, reduce, commit],
  );

  // 发送一条新消息;body 为这一轮要附加的请求字段(如 RAG 的 conversation_id)
  const send = useCallback(
    (text: string, body?: Record<string, unknown>) => {
      const q = text.trim();
      if (!q) return;
      lastTurn.current = { text: q, body };
      const user: ChatMessage = { id: crypto.randomUUID(), role: "user", text: q };
      stream(q, [...messagesRef.current, user], body);
    },
    [stream],
  );

  // 重试:回退到最后一条 user,用同样的入参重新生成回答(丢弃失败的那条草稿)
  const regenerate = useCallback(() => {
    const t = lastTurn.current;
    if (!t) return;
    const i = messagesRef.current.map((m) => m.role).lastIndexOf("user");
    const base =
      i === -1 ? messagesRef.current : messagesRef.current.slice(0, i + 1);
    stream(t.text, base, t.body);
  }, [stream]);

  const stop = useCallback(() => abortRef.current?.abort(), []);

  // 切换模式时清空当前会话(各模式独立、不混在一起)
  const reset = useCallback(() => {
    abortRef.current?.abort();
    commit([]);
    setStatus("ready");
    setError(null);
  }, [commit]);

  return { messages, status, error, send, regenerate, stop, reset };
}
