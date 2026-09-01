import type { BackendFrame } from "./types";

/**
 * 把后端的自定义 SSE 响应体切成一帧帧并 JSON.parse。
 *
 * 后端把每帧编码为 `data: {json}\n\n`(app/routers/query.py: _sse)。
 * 这里用 TextDecoder({stream:true}) 处理跨 chunk 的多字节字符,
 * 再用 buffer 按事件分隔符 `\n\n` 切块(参考后端 web/index.html 的 streamQuery)。
 *
 * 以 async generator 形式 yield 每一帧,调用方 `for await` 消费。
 */
export async function* parseSSE<T = BackendFrame>(
  body: ReadableStream<Uint8Array>,
): AsyncGenerator<T> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let idx: number;
      while ((idx = buffer.indexOf("\n\n")) !== -1) {
        const block = buffer.slice(0, idx);
        buffer = buffer.slice(idx + 2);
        const frame = parseEventBlock<T>(block);
        if (frame) yield frame;
      }
    }
    // 兜底:flush 解码器 + 处理可能残留的最后一块(正常流以 done\n\n 收尾,这里一般为空)
    buffer += decoder.decode();
    const frame = parseEventBlock<T>(buffer);
    if (frame) yield frame;
  } finally {
    reader.releaseLock();
  }
}

/**
 * 解析单个事件块。SSE 规范允许一个事件有多行 `data:`(按行拼接);
 * 后端是单行 data,这里仍按规范拼接以求稳健。
 */
function parseEventBlock<T>(block: string): T | null {
  const data = block
    .split("\n")
    .filter((line) => line.startsWith("data:"))
    .map((line) => line.slice(5).replace(/^ /, "")) // 去 "data:" 前缀及可选的一个前导空格
    .join("\n");

  if (!data.trim()) return null;
  try {
    return JSON.parse(data) as T;
  } catch {
    // 已按 \n\n 切帧,理论上不会出现半截 JSON;兜底跳过,避免整流崩掉
    return null;
  }
}
