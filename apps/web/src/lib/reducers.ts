import type { AgentFrame, BackendFrame, ChatMessage } from "./types";

/**
 * 把后端 SSE 的一帧累积进 assistant 草稿(原地改 draft)。
 * 这是原 adapter.ts 的内核 —— 去掉了喂 useChat 所需的 text-start/text-end、
 * data-* 部件包装,只剩「这一帧改写消息的哪个字段」。
 *
 * strip 是 <think> 流式剥离器的 push(跨 token 记状态),由 useStreamChat 注入。
 */

/** RAG /query/stream:sources → 引用;token(text) → 正文;done → 回填 conversation_id。 */
export function ragReduce(
  frame: BackendFrame,
  draft: ChatMessage,
  strip: (s: string) => string,
): void {
  switch (frame.type) {
    case "sources":
      draft.sources = frame.sources;
      break;
    case "token":
      draft.text += strip(frame.text);
      break;
    case "done":
      draft.conversationId = frame.conversation_id;
      break;
    case "error":
      // 开流后中途失败:抛出,由 useStreamChat 的 catch 转成 error 状态
      throw new Error(frame.message || "流式响应错误");
  }
}

/** Agent /agent/stream:token(content) → 正文;step → 工具时间线(同 id 原地 running→done)。 */
export function agentReduce(
  frame: AgentFrame,
  draft: ChatMessage,
  strip: (s: string) => string,
): void {
  switch (frame.type) {
    case "token":
      draft.text += strip(frame.content); // Agent token 字段使用 content
      break;
    case "step":
      if (frame.status === "running") {
        // 新增一条 running 步骤(input 来自 running 帧)
        draft.toolSteps = [
          ...(draft.toolSteps ?? []),
          {
            id: frame.id,
            data: { tool: frame.tool, status: "running", input: frame.input },
          },
        ];
      } else {
        // done 帧只带 output;按 id 找到那条 running 原地补成 done(input 沿用 running 的)
        draft.toolSteps = (draft.toolSteps ?? []).map((s) =>
          s.id === frame.id
            ? { id: s.id, data: { ...s.data, status: "done", output: frame.output } }
            : s,
        );
      }
      break;
    case "error":
      throw new Error(frame.message || "Agent 流式响应错误");
    case "done":
      break; // agent 无 conversation_id / 无 sources,done 不带额外信息
  }
}
