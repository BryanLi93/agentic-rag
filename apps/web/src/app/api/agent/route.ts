export const runtime = "nodejs";
export const maxDuration = 60;

const AGENT_API_BASE = process.env.AGENT_API_BASE ?? "http://127.0.0.1:8100";

const SSE_HEADERS = {
  "Content-Type": "text/event-stream; charset=utf-8",
  "Cache-Control": "no-cache, no-transform",
  Connection: "keep-alive",
};

export async function POST(req: Request) {
  const { question } = (await req.json()) as { question?: string };
  const q = question?.trim();
  if (!q) return new Response("问题不能为空", { status: 400 });

  let upstream: Response;
  try {
    upstream = await fetch(`${AGENT_API_BASE}/agent/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: q }),
    });
  } catch {
    return new Response("连接不上 Agent 服务(:8100),它起着吗?", {
      status: 502,
    });
  }

  if (!upstream.ok || !upstream.body) {
    const detail = await upstream.text().catch(() => "");
    return new Response(detail || `上游服务错误 ${upstream.status}`, {
      status: upstream.status || 502,
    });
  }

  // agent /agent/stream 的 SSE 直接透传,客户端 parseSSE + agentReduce 解析
  return new Response(upstream.body, { headers: SSE_HEADERS });
}
