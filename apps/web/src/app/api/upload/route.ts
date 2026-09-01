import type { NextRequest } from "next/server";

export const runtime = "nodejs";
export const maxDuration = 60;

const RAG_API_BASE = process.env.RAG_API_BASE ?? "http://127.0.0.1:8000";

// 透传上传到 RAG /upload(multipart)。读出 form 里的 file,再以 multipart 转发。
export async function POST(req: NextRequest) {
  const form = await req.formData();
  const file = form.get("file");
  if (!(file instanceof File)) {
    return new Response("缺少文件字段 file", { status: 400 });
  }

  const fd = new FormData();
  fd.append("file", file, file.name);

  const upstream = await fetch(`${RAG_API_BASE}/upload`, {
    method: "POST",
    body: fd,
  });

  // 原样回传状态码 + body(成功 201 带 chunk_count;失败带后端错误详情)
  const body = await upstream.text();
  return new Response(body, {
    status: upstream.status,
    headers: {
      "Content-Type":
        upstream.headers.get("content-type") ?? "application/json",
    },
  });
}
