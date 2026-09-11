export const runtime = "nodejs";
export const maxDuration = 60;

const AGENT_API_BASE = process.env.AGENT_API_BASE ?? "http://127.0.0.1:8100";

export async function POST(req: Request) {
  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return new Response("请求必须是 JSON", { status: 400 });
  }
  if (typeof body !== "object" || body === null || !("question" in body) ||
      typeof body.question !== "string") {
    return new Response("问题必须是字符串", { status: 400 });
  }
  const question = body.question.trim();
  if (!question || question.length > 1000) {
    return new Response("问题长度必须为 1–1000 个字符", { status: 400 });
  }
  let thread_id: string | undefined;
  if ("thread_id" in body && body.thread_id != null) {
    if (typeof body.thread_id !== "string" || !/^[A-Za-z0-9_-]{1,128}$/.test(body.thread_id)) {
      return new Response("thread_id 格式不正确", { status: 400 });
    }
    thread_id = body.thread_id;
  }

  let upstream: Response;
  try {
    upstream = await fetch(`${AGENT_API_BASE}/agent/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, thread_id }),
      signal: req.signal,
      cache: "no-store",
    });
  } catch {
    return new Response("无法连接 Agent 服务", { status: 502 });
  }
  if (!upstream.ok || !upstream.body) {
    const detail = await upstream.text().catch(() => "");
    return new Response(detail || "Agent 服务响应异常", {
      status: upstream.ok ? 502 : upstream.status,
    });
  }
  // 原样转发 sources、step、token、done、error，上传不经过此路由。
  return new Response(upstream.body, {
    headers: {
      "Content-Type": "text/event-stream; charset=utf-8",
      "Cache-Control": "no-cache, no-transform",
      "X-Accel-Buffering": "no",
    },
  });
}
