// 需要服务端流式 fetch + 长连接,用 Node runtime(默认即是);给足时长上限。
export const runtime = "nodejs";
export const maxDuration = 60;

const RAG_API_BASE = process.env.RAG_API_BASE ?? "http://127.0.0.1:8000";

// SSE 透传头:把后端 text/event-stream 原样转给浏览器,关掉中间层缓冲。
const SSE_HEADERS = {
  "Content-Type": "text/event-stream; charset=utf-8",
  "Cache-Control": "no-cache, no-transform",
  Connection: "keep-alive",
};

export async function POST(req: Request) {
  const { question, conversation_id } = (await req.json()) as {
    question?: string;
    conversation_id?: string;
  };
  const q = question?.trim();
  if (!q) return new Response("问题不能为空", { status: 400 });

  // 调后端 /query/stream;后端没起/连不上时给一个干净的 502(否则 fetch 抛出会变成 500)
  let upstream: Response;
  try {
    upstream = await fetch(`${RAG_API_BASE}/query/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question: q,
        top_k: 5,
        ...(conversation_id ? { conversation_id } : {}),
      }),
    });
  } catch {
    return new Response("连接不上 RAG 服务(:8000),它起着吗?", { status: 502 });
  }

  // 开流前错误(会话不存在 404 / 检索失败 502):此时还没发 200,直接把状态码映射给客户端
  if (!upstream.ok || !upstream.body) {
    const detail = await upstream.text().catch(() => "");
    return new Response(detail || `上游服务错误 ${upstream.status}`, {
      status: upstream.status || 502,
    });
  }

  // 开流后:后端 SSE 直接透传,客户端 parseSSE 自己解析每帧
  return new Response(upstream.body, { headers: SSE_HEADERS });
}
