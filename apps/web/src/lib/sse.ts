/**
 * 把后端的自定义 SSE 响应体切成一帧帧并 JSON.parse。
 *
 * 后端把每帧编码为 `data: {json}\n\n`(app/routers/query.py: _sse)。
 * 这里用 TextDecoder({stream:true}) 处理跨 chunk 的多字节字符,
 * 再用 buffer 按事件分隔符 `\n\n` 切块(参考后端 web/index.html 的 streamQuery)。
 *
 * 以 async generator 形式 yield 每一帧,调用方 `for await` 消费。
 */
export async function* parseSSE(
  body: ReadableStream<Uint8Array>,
): AsyncGenerator<unknown> {
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
        const frame = parseEventBlock(block);
        if (frame !== null) yield frame;
      }
    }
    // 兜底:flush 解码器 + 处理可能残留的最后一块(正常流以 done\n\n 收尾,这里一般为空)
    buffer += decoder.decode();
    const frame = parseEventBlock(buffer);
    if (frame !== null) yield frame;
  } finally {
    try {
      await reader.cancel();
    } finally {
      reader.releaseLock();
    }
  }
}

/**
 * 解析单个事件块。SSE 规范允许一个事件有多行 `data:`(按行拼接);
 * 后端是单行 data,这里仍按规范拼接以求稳健。
 */
function parseEventBlock(block: string): unknown {
  const data = block
    .split("\n")
    .filter((line) => line.startsWith("data:"))
    .map((line) => line.slice(5).replace(/^ /, "")) // 去 "data:" 前缀及可选的一个前导空格
    .join("\n");

  if (!data.trim()) return null;
  try {
    return JSON.parse(data);
  } catch {
    throw new Error("SSE 消息不是有效 JSON");
  }
}
