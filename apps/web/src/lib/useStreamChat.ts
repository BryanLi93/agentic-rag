"use client";

import { useCallback, useRef, useState } from "react";
import { parseSSE } from "./sse";
import { isChatFrame } from "./chat-frame";
import { chatReduce } from "./reducers";
import { createThinkStripper } from "./think";
import type { ChatMessage } from "./types";

export type ChatStatus = "ready" | "streaming" | "error";

/** 唯一聊天入口；会话 ID 独立于消息列表，不从某条失败草稿中推断。 */
export function useStreamChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [status, setStatus] = useState<ChatStatus>("ready");
  const [error, setError] = useState<Error | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const messagesRef = useRef<ChatMessage[]>([]);
  const threadRef = useRef<string | null>(null);
  const lastQuestion = useRef("");

  const commit = useCallback((next: ChatMessage[]) => {
    messagesRef.current = next;
    setMessages(next);
  }, []);

  const send = useCallback(async (text: string) => {
    const question = text.trim();
    if (!question || abortRef.current) return;
    if (!threadRef.current) threadRef.current = crypto.randomUUID();
    const threadId = threadRef.current;
    const ac = new AbortController();
    abortRef.current = ac;
    lastQuestion.current = question;
    const user: ChatMessage = { id: crypto.randomUUID(), role: "user", text: question };
    const draft: ChatMessage = { id: crypto.randomUUID(), role: "assistant", text: "" };
    commit([...messagesRef.current, user, draft]);
    setStatus("streaming");
    setError(null);
    const strip = createThinkStripper();
    let completed = false;

    // reset 后旧请求即使晚到，也不能改写新会话的消息或状态。
    const isCurrent = () => abortRef.current === ac;
    const flush = () => {
      if (isCurrent()) {
        commit(messagesRef.current.map(message => message.id === draft.id ? { ...draft } : message));
      }
    };
    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, thread_id: threadId }),
        signal: ac.signal,
      });
      if (!res.ok || !res.body) throw new Error((await res.text()) || `HTTP ${res.status}`);
      for await (const frame of parseSSE(res.body)) {
        if (!isCurrent()) break;
        if (!isChatFrame(frame)) throw new Error("无法识别聊天事件");
        if (frame.type === "done" && frame.thread_id !== threadId) {
          throw new Error("服务返回的会话 ID 与请求不一致");
        }
        chatReduce(frame, draft, strip.push);
        flush();
        if (frame.type === "done") {
          threadRef.current = frame.thread_id;
          completed = true;
          break;
        }
      }
      if (!isCurrent()) return;
      if (!completed) throw new Error("回答流意外结束，请重新发送或新建对话");
      draft.text += strip.flush();
      flush();
      setStatus("ready");
    } catch (reason) {
      if (!isCurrent()) return;
      draft.text += strip.flush();
      flush();
      if (ac.signal.aborted) {
        setStatus("ready");
      } else {
        setError(reason instanceof Error ? reason : new Error(String(reason)));
        setStatus("error");
      }
    } finally {
      if (isCurrent()) abortRef.current = null;
    }
  }, [commit]);

  // 后端没有回滚/幂等：重新发送作为新一轮追加，不删除旧消息假装重新生成。
  const resend = useCallback(() => { return send(lastQuestion.current); }, [send]);
  const stop = useCallback(() => { abortRef.current?.abort(); }, []);
  const reset = useCallback(() => {
    const previous = abortRef.current;
    abortRef.current = null;
    previous?.abort();
    threadRef.current = null;
    lastQuestion.current = "";
    commit([]);
    setStatus("ready");
    setError(null);
  }, [commit]);

  return { messages, status, error, send, resend, stop, reset };
}
