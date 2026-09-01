"use client";

import { useState } from "react";
import type { ToolStepData } from "@/lib/types";

/** Agent 模式:工具调用时间线。每步 running→done 由 SDK 按部件 id 原地更新。 */
export function ToolTimeline({
  steps,
}: {
  steps: { id: string; data: ToolStepData }[];
}) {
  return (
    <div className="mb-2 space-y-1">
      {steps.map((s) => (
        <ToolStep key={s.id} data={s.data} />
      ))}
    </div>
  );
}

function ToolStep({ data }: { data: ToolStepData }) {
  const [open, setOpen] = useState(false);
  const running = data.status === "running";
  return (
    <div className="rounded-lg border border-black/10 bg-black/[0.03] text-xs dark:border-white/10 dark:bg-white/[0.04]">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-2 px-2 py-1 text-left"
      >
        <span
          className={
            running
              ? "animate-pulse"
              : "text-green-600 dark:text-green-400"
          }
        >
          {running ? "⏳" : "✓"}
        </span>
        <span className="text-zinc-700 dark:text-zinc-300">
          {running ? "正在调用" : "已调用"}{" "}
          <span className="font-mono font-medium">{data.tool}</span>
        </span>
        <span className="ml-auto text-zinc-400">{open ? "▾" : "▸"}</span>
      </button>
      {open && (
        <div className="space-y-1.5 border-t border-black/10 px-2 py-1.5 dark:border-white/10">
          {data.input && (
            <div>
              <div className="mb-0.5 text-zinc-400">入参</div>
              <pre className="overflow-x-auto whitespace-pre-wrap text-zinc-600 dark:text-zinc-400">
                {JSON.stringify(data.input, null, 2)}
              </pre>
            </div>
          )}
          {data.output && (
            <div>
              <div className="mb-0.5 text-zinc-400">返回</div>
              <pre className="max-h-40 overflow-auto whitespace-pre-wrap text-zinc-600 dark:text-zinc-400">
                {data.output}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
