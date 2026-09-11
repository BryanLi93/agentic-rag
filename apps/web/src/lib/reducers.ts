import type { ChatFrame, ChatMessage, Source } from "./types";

/** 更新当前回答，不改动上一轮的正文、来源或工具轨迹。 */
export function chatReduce(
  frame: ChatFrame,
  draft: ChatMessage,
  strip: (text: string) => string,
): void {
  switch (frame.type) {
    case "sources": {
      draft.sourceGroups = { ...draft.sourceGroups, [frame.tool_call_id]: frame.sources };
      const byId = new Map<number, Source>();
      const conflicts = new Set<number>();
      for (const group of Object.values(draft.sourceGroups)) {
        for (const source of group) {
          const previous = byId.get(source.id);
          if (previous && (previous.chunk_id !== source.chunk_id ||
              previous.document_id !== source.document_id || previous.content !== source.content)) {
            conflicts.add(source.id);
          }
          byId.set(source.id, source);
        }
      }
      // 后端每次检索独立编号，前端不能擅自改号或把 [1] 指向错误原文。
      draft.sources = Array.from(byId.values()).filter(source => !conflicts.has(source.id));
      draft.sourceWarning = conflicts.size > 0
        ? "多次检索出现重复引用编号，冲突编号暂不支持点击；原文可在工具执行结果中查看。"
        : undefined;
      break;
    }
    case "token":
      draft.text += strip(frame.content);
      break;
    case "step": {
      const steps = draft.toolSteps ?? [];
      const index = steps.findIndex(step => step.id === frame.id);
      const previous = index >= 0 ? steps[index].data : undefined;
      const data = frame.status === "running"
        ? { tool: frame.tool, status: frame.status, input: frame.input }
        : { ...previous, tool: frame.tool, status: frame.status, output: frame.output };
      const updated = [...steps];
      if (index >= 0) updated[index] = { id: frame.id, data };
      else updated.push({ id: frame.id, data });
      draft.toolSteps = updated;
      break;
    }
    case "done":
      draft.threadId = frame.thread_id;
      break;
    case "error":
      throw new Error(frame.message || "Agent 流式响应错误");
  }
}
