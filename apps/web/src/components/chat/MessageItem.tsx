"use client";

import { useCallback, useMemo, useState } from "react";
import type { ChatMessage, Source } from "@/lib/types";
import { MessageContent } from "./MessageContent";
import { ToolTimeline } from "./ToolTimeline";
import { getSources, getText, getToolSteps } from "./message-utils";

export function MessageItem({
  message,
  busy,
  onActivateSources,
}: {
  message: ChatMessage;
  busy: boolean;
  // 点 [n] 或「来源」按钮:把本条消息的 sources 灌进侧边栏(ref=要定位的编号,null=只打开)
  onActivateSources: (sources: Source[], ref: number | null) => void;
}) {
  const isUser = message.role === "user";
  const text = getText(message);
  // 按 message 引用缓存:消息定型后引用稳定 → sources/validIds/onCite 都稳定,
  // 不会在别的消息流式刷新时把本条 Markdown 的 memo 打穿(只有正在流的那条会重算)
  const sources = useMemo(() => getSources(message), [message]);
  const toolSteps = getToolSteps(message);
  const validIds = useMemo(() => new Set(sources.map((s) => s.id)), [sources]);

  const [feedback, setFeedback] = useState<"up" | "down" | null>(null);

  const onCite = useCallback(
    (n: number) => onActivateSources(sources, n),
    [onActivateSources, sources],
  );

  if (isUser) {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] rounded-2xl bg-blue-600 px-4 py-2 text-sm whitespace-pre-wrap break-words text-white">
          {text}
        </div>
      </div>
    );
  }

  return (
    <div className="flex justify-start">
      <div className="max-w-[85%] rounded-2xl bg-black/5 px-4 py-2 text-sm dark:bg-white/10">
        {/* agent 模式:工具时间线在答案上方(它是为了产出答案而做的工作) */}
        {toolSteps.length > 0 && <ToolTimeline steps={toolSteps} />}

        <MessageContent text={text} validIds={validIds} onCite={onCite} />

        {!text && busy && (
          <span className="inline-block animate-pulse text-zinc-400">
            思考中…
          </span>
        )}

        {/* 底部操作行:来源入口(打开侧边栏)+ 反馈 */}
        {text && !busy && (
          <div className="mt-2 flex items-center gap-2 text-zinc-400">
            {sources.length > 0 && (
              <button
                type="button"
                onClick={() => onActivateSources(sources, null)}
                className="rounded px-1.5 py-0.5 text-xs hover:bg-black/5 hover:text-zinc-600 dark:hover:bg-white/10 dark:hover:text-zinc-300"
              >
                📚 来源 {sources.length}
              </button>
            )}
            <button
              type="button"
              onClick={() => setFeedback((f) => (f === "up" ? null : "up"))}
              title="有帮助"
              className={`rounded px-1.5 py-0.5 text-sm hover:bg-black/5 dark:hover:bg-white/10 ${
                feedback === "up" ? "text-green-600 dark:text-green-400" : ""
              }`}
            >
              👍
            </button>
            <button
              type="button"
              onClick={() => setFeedback((f) => (f === "down" ? null : "down"))}
              title="没帮助"
              className={`rounded px-1.5 py-0.5 text-sm hover:bg-black/5 dark:hover:bg-white/10 ${
                feedback === "down" ? "text-red-600 dark:text-red-400" : ""
              }`}
            >
              👎
            </button>
            {feedback && <span className="text-xs">谢谢反馈</span>}
          </div>
        )}
      </div>
    </div>
  );
}
