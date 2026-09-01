"use client";

import { useEffect, useRef, useState } from "react";
import type { Source } from "@/lib/types";

/**
 * 引用来源侧边栏(W12 #1)。
 * - 桌面(lg+):常驻右栏(static,占 320px)。
 * - 移动端:从右侧滑入的抽屉(fixed + transform),带遮罩。
 * 点答案里的 [n] 会把对应消息的 sources 灌进来,并定位/高亮/展开第 n 张卡片。
 */
export function SourcesPanel({
  sources,
  activeRef,
  activeKey,
  open,
  onClose,
}: {
  sources: Source[];
  activeRef: number | null; // 要定位的来源编号
  activeKey: number; // 每次点击自增,保证重复点同一个 [n] 也重新触发
  open: boolean; // 移动端抽屉是否打开
  onClose: () => void;
}) {
  // 用户手动额外展开的卡片;当前定位的那张(activeRef)由 props 派生为展开+高亮,无需 setState
  const [openCards, setOpenCards] = useState<Set<number>>(new Set());
  const cardRefs = useRef<Record<number, HTMLDivElement | null>>({});

  // 点 [n] 只做滚动(纯 DOM 副作用,不在 effect 里 setState);展开/高亮由下面派生
  useEffect(() => {
    if (activeRef == null) return;
    const raf = requestAnimationFrame(() =>
      cardRefs.current[activeRef]?.scrollIntoView({
        behavior: "smooth",
        block: "center",
      }),
    );
    return () => cancelAnimationFrame(raf);
  }, [activeRef, activeKey]);

  const toggle = (n: number) =>
    setOpenCards((prev) => {
      const s = new Set(prev);
      if (s.has(n)) s.delete(n);
      else s.add(n);
      return s;
    });

  return (
    <>
      {/* 移动端遮罩 */}
      {open && (
        <div
          onClick={onClose}
          className="fixed inset-0 z-30 bg-black/30 lg:hidden"
        />
      )}

      <aside
        className={`fixed inset-y-0 right-0 z-40 flex w-80 max-w-[85vw] transform flex-col border-l border-black/10 bg-[var(--background)] transition-transform dark:border-white/10 lg:static lg:z-auto lg:max-w-none lg:transform-none ${
          open ? "translate-x-0 shadow-xl" : "translate-x-full"
        } lg:translate-x-0`}
      >
        <div className="flex items-center justify-between border-b border-black/10 px-4 py-3 dark:border-white/10">
          <h2 className="text-sm font-semibold">
            引用来源{sources.length > 0 ? ` · ${sources.length}` : ""}
          </h2>
          <button
            onClick={onClose}
            className="text-zinc-400 hover:text-zinc-600 lg:hidden"
            aria-label="关闭"
          >
            ✕
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-3">
          {sources.length === 0 ? (
            <p className="mt-6 px-2 text-center text-xs text-zinc-400">
              回答中的来源会显示在这里。点蓝色的 [n] 可定位到对应原文片段。
            </p>
          ) : (
            <div className="space-y-2">
              {sources.map((s) => (
                <SourceCard
                  key={s.id}
                  source={s}
                  open={openCards.has(s.id) || s.id === activeRef}
                  highlighted={s.id === activeRef}
                  onToggle={() => toggle(s.id)}
                  cardRef={(el) => {
                    cardRefs.current[s.id] = el;
                  }}
                />
              ))}
            </div>
          )}
        </div>
      </aside>
    </>
  );
}

function SourceCard({
  source,
  open,
  highlighted,
  onToggle,
  cardRef,
}: {
  source: Source;
  open: boolean;
  highlighted: boolean;
  onToggle: () => void;
  cardRef: (el: HTMLDivElement | null) => void;
}) {
  return (
    <div
      ref={cardRef}
      className={`scroll-mt-2 rounded-lg border text-xs transition-colors ${
        highlighted
          ? "border-blue-400 bg-blue-50 dark:border-blue-500 dark:bg-blue-950/40"
          : "border-black/10 dark:border-white/10"
      }`}
    >
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-center gap-2 px-2 py-1.5 text-left"
      >
        <span className="font-mono font-semibold text-blue-600 dark:text-blue-400">
          [{source.id}]
        </span>
        <span className="truncate text-zinc-700 dark:text-zinc-300">
          {source.document_filename}
        </span>
        <span className="ml-auto shrink-0 text-zinc-400">
          {(source.similarity * 100).toFixed(0)}%
        </span>
        <span className="shrink-0 text-zinc-400">{open ? "▾" : "▸"}</span>
      </button>
      {open && (
        <p className="border-t border-black/10 px-2 py-1.5 whitespace-pre-wrap text-zinc-600 dark:border-white/10 dark:text-zinc-400">
          {source.content}
        </p>
      )}
    </div>
  );
}
