import type { ChatFrame, Source } from "./types";

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isSource(value: unknown): value is Source {
  if (!isObject(value)) return false;
  for (const key of ["id", "chunk_id", "document_id", "chunk_index"]) {
    if (!Number.isInteger(value[key])) return false;
  }
  for (const key of ["vector_rank", "keyword_rank", "rerank_score"]) {
    if (value[key] != null && typeof value[key] !== "number") return false;
  }
  return typeof value.document_filename === "string" &&
    typeof value.content === "string" && typeof value.similarity === "number";
}

/** JSON 是不可信边界，校验后再交给 reducer，不用类型断言掩盖错误。 */
export function isChatFrame(value: unknown): value is ChatFrame {
  if (!isObject(value)) return false;
  switch (value.type) {
    case "token": return typeof value.content === "string";
    case "done": return typeof value.thread_id === "string" && /^[A-Za-z0-9_-]{1,128}$/.test(value.thread_id);
    case "error": return typeof value.message === "string";
    case "sources": return typeof value.tool_call_id === "string" &&
      Array.isArray(value.sources) && value.sources.every(isSource);
    case "step":
      if (typeof value.id !== "string" || typeof value.tool !== "string") return false;
      if (value.status === "running") return isObject(value.input);
      return value.status === "done" && typeof value.output === "string";
    default: return false;
  }
}
