"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { Source } from "@/lib/types";
import { type Reduce, useStreamChat } from "@/lib/useStreamChat";
import { agentReduce, ragReduce } from "@/lib/reducers";
import { uploadFile, validateFile } from "@/lib/upload";
import { MessageItem } from "./MessageItem";
import { SourcesPanel } from "./SourcesPanel";
import { getSources } from "./message-utils";

// 侧边栏当前展示的来源 + 要定位的编号;key 每次激活自增,保证重复点同一个 [n] 也能重新触发定位
type ActiveSources = { sources: Source[]; ref: number | null; key: number };

type UploadState = {
  name: string;
  pct: number;
  status: "uploading" | "done" | "error";
  chunkCount?: number;
  error?: string;
};

type Mode = "rag" | "agent";

const SAMPLES: Record<Mode, string[]> = {
  rag: ["什么是 RAG?", "向量检索和关键词检索有什么区别?"],
  agent: ["pgvector 用什么距离度量?", "FastAPI 的请求流程是怎样的?"],
};

export function Chat() {
  const [mode, setMode] = useState<Mode>("rag");
  const [input, setInput] = useState("");
  const [upload, setUpload] = useState<UploadState | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [active, setActive] = useState<ActiveSources>({
    sources: [],
    ref: null,
    key: 0,
  });
  const [panelOpen, setPanelOpen] = useState(false); // 移动端抽屉
  const scrollRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const lastFollowKey = useRef("");

  // 自定义流式 hook 包办 messages / 状态 / 停止 / 重试;按 mode 选 endpoint 和帧解析逻辑
  const { messages, send: sendMessage, status, error, regenerate, stop, reset } =
    useStreamChat({
      api: mode === "agent" ? "/api/agent" : "/api/chat",
      reduce: (mode === "agent" ? agentReduce : ragReduce) as Reduce,
    });

  const busy = status === "streaming";

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [messages]);

  // 点 [n] 或「来源」按钮:把该消息的 sources 灌进侧边栏并(移动端)打开抽屉
  const activateSources = useCallback((sources: Source[], ref: number | null) => {
    setActive((a) => ({ sources, ref, key: a.key + 1 }));
    setPanelOpen(true); // 移动端弹出抽屉;桌面端侧栏本就常驻
  }, []);

  // 自动跟随:新答案的来源到达后,侧边栏默认显示最新一条(不抢用户手动点开的旧消息焦点)
  useEffect(() => {
    const lastAssistant = [...messages]
      .reverse()
      .find((m) => m.role === "assistant");
    const src = lastAssistant ? getSources(lastAssistant) : [];
    const followKey = `${lastAssistant?.id ?? ""}:${src.map((s) => s.id).join(",")}`;
    if (src.length > 0 && followKey !== lastFollowKey.current) {
      lastFollowKey.current = followKey;
      setActive((a) => ({ ...a, sources: src })); // 只换列表,不动 ref/key(不触发定位高亮)
    }
  }, [messages]);

  function send(text: string) {
    const q = text.trim();
    if (!q || busy) return;
    setInput("");
    // RAG 多轮:从最近一条 assistant 回填的 conversationId 带给后端;agent 无多轮
    const conversationId =
      mode === "rag"
        ? [...messages].reverse().find((m) => m.role === "assistant")
            ?.conversationId
        : undefined;
    sendMessage(q, conversationId ? { conversation_id: conversationId } : undefined);
  }

  function switchMode(next: Mode) {
    if (next === mode) return;
    reset(); // 各模式会话独立,切换即清空当前消息
    // 来源侧栏也清空(agent 模式无结构化来源)
    setActive({ sources: [], ref: null, key: 0 });
    setPanelOpen(false);
    lastFollowKey.current = "";
    setMode(next);
  }

  async function handleFile(file: File) {
    const err = validateFile(file);
    if (err) {
      setUpload({ name: file.name, pct: 0, status: "error", error: err });
      return;
    }
    setUpload({ name: file.name, pct: 0, status: "uploading" });
    try {
      const res = await uploadFile(file, (pct) =>
        setUpload((u) => (u ? { ...u, pct } : u)),
      );
      setUpload({
        name: res.filename,
        pct: 100,
        status: "done",
        chunkCount: res.chunk_count,
      });
    } catch (e) {
      setUpload({
        name: file.name,
        pct: 0,
        status: "error",
        error: e instanceof Error ? e.message : "上传失败",
      });
    }
  }

  function onDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files?.[0];
    if (file) handleFile(file);
  }

  return (
    <div className="flex h-dvh w-full">
      <div className="mx-auto flex min-w-0 max-w-3xl flex-1 flex-col">
      <header className="flex items-center justify-between border-b border-black/10 px-4 py-3 dark:border-white/10">
        <div>
          <h1 className="text-sm font-semibold">AgenticRAG</h1>
          <p className="text-xs text-zinc-500">
            {mode === "rag"
              ? "知识库问答 · 流式回答 · 引用溯源"
              : "Agent · 知识库工具 · 执行轨迹"}
          </p>
        </div>
        {/* 模式切换:RAG 直连 / Agent(带工具可视化) */}
        <div className="flex rounded-full border border-black/10 p-0.5 text-xs dark:border-white/15">
          {(["rag", "agent"] as const).map((m) => (
            <button
              key={m}
              onClick={() => switchMode(m)}
              className={`rounded-full px-3 py-1 transition-colors ${
                mode === m
                  ? "bg-blue-600 text-white"
                  : "text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-200"
              }`}
            >
              {m === "rag" ? "RAG" : "Agent"}
            </button>
          ))}
        </div>
      </header>

      <div
        ref={scrollRef}
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={onDrop}
        className="relative flex-1 space-y-4 overflow-y-auto p-4"
      >
        {dragOver && (
          <div className="pointer-events-none absolute inset-2 z-10 flex items-center justify-center rounded-xl border-2 border-dashed border-blue-400 bg-blue-50/80 text-sm font-medium text-blue-600 dark:bg-blue-950/70 dark:text-blue-300">
            松手上传文档(.txt / .md / .pdf)
          </div>
        )}
        {messages.length === 0 && (
          <div className="mt-10 text-center text-sm text-zinc-500">
            <p className="mb-4">
              {mode === "rag"
                ? "问点知识库里的内容试试:"
                : "Agent 会自己决定要不要查知识库工具:"}
            </p>
            <div className="flex flex-col items-center gap-2">
              {SAMPLES[mode].map((s) => (
                <button
                  key={s}
                  onClick={() => send(s)}
                  className="rounded-full border border-black/10 px-4 py-1.5 text-sm transition-colors hover:bg-black/5 dark:border-white/15 dark:hover:bg-white/5"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((m) => (
          <MessageItem
            key={m.id}
            message={m}
            busy={busy}
            onActivateSources={activateSources}
          />
        ))}

        {error && (
          <div className="flex items-center gap-3 rounded-lg border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-800 dark:bg-red-950 dark:text-red-300">
            <span className="flex-1">出错了:{error.message}</span>
            <button
              onClick={() => regenerate()}
              className="shrink-0 rounded-md bg-red-600 px-2 py-1 text-xs font-medium text-white"
            >
              重试
            </button>
          </div>
        )}
      </div>

      {upload && (
        <div className="border-t border-black/10 px-3 pt-2 text-xs dark:border-white/10">
          {upload.status === "uploading" && (
            <div>
              <div className="mb-1 text-zinc-500">
                上传中 {upload.name} · {upload.pct}%
              </div>
              <div className="h-1.5 w-full overflow-hidden rounded bg-black/10 dark:bg-white/10">
                <div
                  className="h-full bg-blue-600 transition-all"
                  style={{ width: `${upload.pct}%` }}
                />
              </div>
            </div>
          )}
          {upload.status === "done" && (
            <div className="flex items-center gap-2 text-green-600 dark:text-green-400">
              <span>
                ✓ 已上传 {upload.name} · {upload.chunkCount} 块,可以直接问这篇文档了
              </span>
              <button
                onClick={() => setUpload(null)}
                className="ml-auto text-zinc-400 hover:text-zinc-600"
              >
                ✕
              </button>
            </div>
          )}
          {upload.status === "error" && (
            <div className="flex items-center gap-2 text-red-600 dark:text-red-400">
              <span>上传失败:{upload.error}</span>
              <button
                onClick={() => setUpload(null)}
                className="ml-auto text-zinc-400 hover:text-zinc-600"
              >
                ✕
              </button>
            </div>
          )}
        </div>
      )}

      <form
        onSubmit={(e) => {
          e.preventDefault();
          send(input);
        }}
        className="border-t border-black/10 p-3 dark:border-white/10"
      >
        <div className="flex items-end gap-2">
          <input
            ref={fileInputRef}
            type="file"
            accept=".txt,.md,.markdown,.pdf"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) handleFile(f);
              e.target.value = "";
            }}
          />
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            title="上传文档(.txt / .md / .pdf)"
            className="rounded-xl border border-black/15 px-3 py-2 text-sm text-zinc-500 hover:bg-black/5 dark:border-white/15 dark:hover:bg-white/5"
          >
            📎
          </button>
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send(input);
              }
            }}
            rows={1}
            placeholder="问点什么…(Enter 发送,Shift+Enter 换行)"
            className="max-h-40 flex-1 resize-none rounded-xl border border-black/15 bg-transparent px-3 py-2 text-sm outline-none focus:border-blue-500 dark:border-white/15"
          />
          {busy ? (
            <button
              type="button"
              onClick={() => stop()}
              className="rounded-xl border border-black/15 px-4 py-2 text-sm font-medium hover:bg-black/5 dark:border-white/15 dark:hover:bg-white/5"
            >
              停止
            </button>
          ) : (
            <button
              type="submit"
              disabled={!input.trim()}
              className="rounded-xl bg-blue-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-40"
            >
              发送
            </button>
          )}
        </div>
      </form>
      </div>

      <SourcesPanel
        sources={active.sources}
        activeRef={active.ref}
        activeKey={active.key}
        open={panelOpen}
        onClose={() => setPanelOpen(false)}
      />
    </div>
  );
}
