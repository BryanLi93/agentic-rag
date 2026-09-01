import type { ChatMessage, Source, ToolStepData } from "@/lib/types";

// 旧版从 message.parts 里 filter/find;现在消息已平铺成字段,直接取。
// 签名保持不变 → MessageItem / ToolTimeline / SourcesPanel 无需改动。

export function getText(m: ChatMessage): string {
  return m.text;
}

export function getSources(m: ChatMessage): Source[] {
  return m.sources ?? [];
}

export function getToolSteps(
  m: ChatMessage,
): { id: string; data: ToolStepData }[] {
  return m.toolSteps ?? [];
}
