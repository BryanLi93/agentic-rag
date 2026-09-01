/**
 * 流式剥离 <think>...</think> 段。
 *
 * 中转站模型(gpt-5.4)会在答案正文前先吐一段 <think> 推理。因为 token 是逐段到达的,
 * `<think>` / `</think>` 标记本身可能被切在两个 token 里,所以不能简单做 String.replace。
 * 这里用一个能跨 chunk 记状态、并按需 hold-back「半截标记」的状态机:
 *
 *   - text 模式:正常输出,但若 buffer 末尾是 `<think>` 的某个前缀,就留到下一段再判断;
 *   - think 模式:丢弃正文,直到出现 `</think>`;同样 hold-back 半截的结束标记。
 *
 * 用法:const s = createThinkStripper(); s.push(tokenChunk) 返回应输出的正文;
 * 流结束调 s.flush() 拿可能残留的尾巴。
 */
const OPEN = "<think>";
const CLOSE = "</think>";

/**
 * 返回 buf 中「可以安全消费(输出或丢弃)」的长度。
 * 若 buf 末尾恰是 tag 的某个前缀(可能是被切断的标记),就把那段留下,等下一段拼接后再判断。
 */
function safeLen(buf: string, tag: string): number {
  const max = Math.min(buf.length, tag.length - 1);
  for (let k = max; k > 0; k--) {
    if (tag.startsWith(buf.slice(buf.length - k))) return buf.length - k;
  }
  return buf.length;
}

export function createThinkStripper() {
  let mode: "text" | "think" = "text";
  let carry = ""; // 跨 chunk 暂存:可能是某个标记的半截

  function push(chunk: string): string {
    let out = "";
    let buf = carry + chunk;
    carry = "";

    while (buf.length > 0) {
      if (mode === "text") {
        const i = buf.indexOf(OPEN);
        if (i === -1) {
          const n = safeLen(buf, OPEN);
          out += buf.slice(0, n);
          carry = buf.slice(n); // 可能是半截 <think>,留到下次
          break;
        }
        out += buf.slice(0, i);
        buf = buf.slice(i + OPEN.length);
        mode = "think";
      } else {
        const i = buf.indexOf(CLOSE);
        if (i === -1) {
          const n = safeLen(buf, CLOSE);
          // n 之前的是 think 正文,丢弃;末尾可能的半截 </think> 留下
          carry = buf.slice(n);
          break;
        }
        buf = buf.slice(i + CLOSE.length);
        mode = "text";
      }
    }
    return out;
  }

  /** 流结束:text 模式下 carry 是真实正文(不是标记),补吐;think 模式下未闭合则丢弃。 */
  function flush(): string {
    const tail = mode === "text" ? carry : "";
    carry = "";
    return tail;
  }

  return { push, flush };
}
