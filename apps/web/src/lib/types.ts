// 与 services/knowledge 的 schema / SSE contract 对齐。

/** /query 与 /query/stream 共用的引用来源结构(app/schemas.py: Source)。 */
export interface Source {
  id: number; // 引用编号,对应答案正文里的 [n] 标记
  chunk_id: number;
  document_id: number;
  document_filename: string; // 侧栏卡片标题
  chunk_index: number;
  content: string; // 卡片正文 / [n] 展开的原文片段
  similarity: number; // 0-1,越高越相关
  vector_rank?: number | null;
  keyword_rank?: number | null;
  rerank_score?: number | null;
}

/** 统一 /api/chat 透传 Agent SSE；工具与文字事件可以多轮交替。 */
export type ChatFrame =
  | { type: "sources"; tool_call_id: string; sources: Source[] }
  | { type: "token"; content: string }
  | { type: "step"; id: string; tool: string; status: "running"; input: Record<string, unknown> }
  | { type: "step"; id: string; tool: string; status: "done"; output: string }
  | { type: "done"; thread_id: string }
  | { type: "error"; message: string };

/** 工具执行步骤(聊天):同一 id 的步骤从 running 重渲染到 done。 */
export interface ToolStepData {
  tool: string;
  status: "running" | "done";
  input?: Record<string, unknown>;
  output?: string;
}

/**
 * 前端消息模型(替代 AI SDK 的 UIMessage.parts[])。
 * 一条 assistant 消息把流式累积的所有信息平铺成字段,渲染端按字段直接取,不再解析 parts 数组:
 *   text          —— 正文(已剥 <think>;聊天把前导+答案拼在一起,工具时间线单独渲在上方)
 *   sources       —— 检索引用来源(sources 帧)
 *   toolSteps     —— Agent 工具时间线(step 帧,按 id 原地 running→done)
 *   threadId      —— Agent done 帧回填,下一轮带上以延续多轮会话
 */
export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  sources?: Source[];
  sourceGroups?: Record<string, Source[]>;
  sourceWarning?: string;
  toolSteps?: { id: string; data: ToolStepData }[];
  threadId?: string;
}
