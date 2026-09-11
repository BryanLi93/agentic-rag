/* eslint-disable @typescript-eslint/no-require-imports -- 本文件是 Node CommonJS 测试入口 */
// 使用现有 TypeScript 编译器和 Node 测试器，不安装测试依赖、不请求真实服务。
const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const ts = require("typescript");

// 只在测试进程内将本地 TS 转成 CommonJS；不写编译产物。
function load(file, overrides = {}) {
  const filename = path.resolve(__dirname, "../src", file);
  const source = ts.transpileModule(fs.readFileSync(filename, "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  }).outputText;
  const loadedModule = { exports: {} };
  const localRequire = name => {
    if (name in overrides) return overrides[name];
    if (name.startsWith(".")) {
      const relative = path.relative(path.resolve(__dirname, "../src"), path.resolve(path.dirname(filename), name + ".ts"));
      return load(relative, overrides);
    }
    return require(name);
  };
  vm.runInThisContext(`(function(require,module,exports){${source}\n})`, { filename })(localRequire, loadedModule, loadedModule.exports);
  return loadedModule.exports;
}

const { chatReduce } = load("lib/reducers.ts");
const { isChatFrame } = load("lib/chat-frame.ts");
const source = { id: 1, chunk_id: 7, document_id: 2, document_filename: "RAG.md", chunk_index: 0, content: "原文", similarity: 0.9 };
const apply = (frame, draft) => chatReduce(frame, draft, text => text);
const sse = frames => frames.map(frame => `data: ${JSON.stringify(frame)}\n\n`).join("");

test("同一回答保存工具轨迹、可点击来源、正文和 thread_id", () => {
  const draft = { id: "m", role: "assistant", text: "" };
  apply({ type: "step", id: "c", tool: "search", status: "running", input: { query: "RAG" } }, draft);
  apply({ type: "sources", tool_call_id: "c", sources: [source] }, draft);
  apply({ type: "step", id: "c", tool: "search", status: "done", output: "原文" }, draft);
  apply({ type: "token", content: "回答[1]" }, draft);
  apply({ type: "done", thread_id: "thread-1" }, draft);
  assert.equal(draft.text, "回答[1]");
  assert.deepEqual(draft.sources, [source]);
  assert.equal(draft.toolSteps.length, 1);
  assert.deepEqual(draft.toolSteps[0].data.input, { query: "RAG" });
  assert.equal(draft.threadId, "thread-1");
});

test("空来源不清空其他工具的来源；重复编号冲突不错误链接", () => {
  const draft = { id: "m", role: "assistant", text: "" };
  apply({ type: "sources", tool_call_id: "a", sources: [source] }, draft);
  apply({ type: "sources", tool_call_id: "b", sources: [] }, draft);
  assert.deepEqual(draft.sources, [source]);
  apply({ type: "sources", tool_call_id: "c", sources: [{ ...source, chunk_id: 8 }] }, draft);
  assert.deepEqual(draft.sources, []);
  assert.match(draft.sourceWarning, /重复引用编号/);
  assert.equal(Object.keys(draft.sourceGroups).length, 3);
});

test("直接回答无来源，error 抛出；消息边界拒绝无效数据", () => {
  const draft = { id: "m", role: "assistant", text: "" };
  apply({ type: "token", content: "你好" }, draft);
  assert.equal(draft.sources, undefined);
  assert.throws(() => apply({ type: "error", message: "失败" }, draft), /失败/);
  assert.equal(isChatFrame({ type: "sources", tool_call_id: "c", sources: [source] }), true);
  assert.equal(isChatFrame({ type: "sources", sources: [{}] }), false);
  assert.equal(isChatFrame({ type: "token", text: "旧协议" }), false);
});

test("SSE 支持中文跨字节分片，中途退出取消底层 reader", async () => {
  const { parseSSE } = load("lib/sse.ts");
  const frames = [{ type: "token", content: "中文" }, { type: "done", thread_id: "t" }];
  const bytes = new TextEncoder().encode(sse(frames));
  const body = new ReadableStream({ start(controller) {
    for (const byte of bytes) controller.enqueue(Uint8Array.of(byte));
    controller.close();
  } });
  const actual = [];
  for await (const frame of parseSSE(body)) actual.push(frame);
  assert.deepEqual(actual, frames);
  let cancelled = false;
  const endless = new ReadableStream({ start(c) { c.enqueue(bytes); }, cancel() { cancelled = true; } });
  for await (const frame of parseSSE(endless)) { assert.ok(frame); break; }
  assert.equal(cancelled, true);
});

test("BFF 只代理 Agent，保留 thread_id、错误状态和取消信号", async () => {
  const route = load("app/api/chat/route.ts");
  const original = global.fetch;
  try {
    global.fetch = async (url, options) => {
      assert.match(url, /\/agent\/stream$/);
      assert.deepEqual(JSON.parse(options.body), { question: "问题", thread_id: "t" });
      assert.ok(options.signal);
      return new Response(sse([{ type: "done", thread_id: "t" }]));
    };
    const request = () => new Request("http://web/api/chat", { method: "POST", body: JSON.stringify({ question: " 问题 ", thread_id: "t" }) });
    assert.match(await (await route.POST(request())).text(), /thread_id/);
    global.fetch = async () => new Response("后端拒绝", { status: 422 });
    assert.equal((await route.POST(request())).status, 422);
    global.fetch = async () => { throw new Error("offline"); };
    assert.equal((await route.POST(request())).status, 502);
    assert.equal((await route.POST(new Request("http://web/api/chat", { method: "POST", body: "{" }))).status, 400);
    assert.equal((await load("app/api/agent/route.ts").POST()).status, 410);
  } finally { global.fetch = original; }
});

// 极小的 hook 状态容器，验证请求状态机；不替代真实浏览器的 React 渲染测试。
function hookHarness() {
  const slots = [];
  let cursor = 0;
  const react = {
    useCallback: callback => callback,
    useRef(value) { const i = cursor++; slots[i] ??= { current: value }; return slots[i]; },
    useState(value) { const i = cursor++; if (!(i in slots)) slots[i] = value; return [slots[i], next => { slots[i] = next; }]; },
  };
  const { useStreamChat } = load("lib/useStreamChat.ts", { react });
  return () => { cursor = 0; return useStreamChat(); };
}

test("两轮复用 ID，新建对话换 ID；重新发送是追加，不替换历史", async () => {
  const render = hookHarness();
  const ids = [];
  const original = global.fetch;
  global.fetch = async (url, options) => {
    assert.equal(url, "/api/chat");
    const body = JSON.parse(options.body);
    ids.push(body.thread_id);
    return new Response(sse([{ type: "token", content: "答" }, { type: "done", thread_id: body.thread_id }]));
  };
  try {
    await render().send("第一轮");
    await render().send("追问");
    assert.equal(ids[0], ids[1]);
    assert.equal(render().messages.length, 4);
    assert.equal(render().messages[1].text, "答");
    await render().resend();
    assert.equal(render().messages.length, 6);
    assert.equal(ids[2], ids[0]);
    render().reset();
    await render().send("新问题");
    assert.notEqual(ids[0], ids[3]);
    assert.equal(render().messages.length, 2);
  } finally { global.fetch = original; }
});

test("新建对话后旧请求晚到不能覆盖新消息或状态", async () => {
  const render = hookHarness();
  const original = global.fetch;
  let finishOld;
  global.fetch = async (url, options) => {
    const body = JSON.parse(options.body);
    if (body.question === "旧") return new Promise(resolve => { finishOld = resolve; });
    return new Response(sse([{ type: "token", content: "新回答" }, { type: "done", thread_id: body.thread_id }]));
  };
  try {
    const old = render().send("旧");
    render().reset();
    await render().send("新");
    finishOld(new Response(sse([{ type: "token", content: "旧回答" }])));
    await old;
    assert.equal(render().messages[1].text, "新回答");
    assert.equal(render().status, "ready");
  } finally { global.fetch = original; }
});

test("缺少 done 的断流不能伪装成功，已显示文字仍保留", async () => {
  const render = hookHarness();
  const original = global.fetch;
  global.fetch = async () => new Response(sse([{ type: "token", content: "部分回答" }]));
  try {
    await render().send("问题");
    assert.equal(render().status, "error");
    assert.equal(render().messages[1].text, "部分回答");
  } finally { global.fetch = original; }
});

test("停止会取消 fetch，不丢弃会话 ID；发送期间阻止重复提交", async () => {
  const render = hookHarness();
  const original = global.fetch;
  const ids = [];
  global.fetch = async (url, options) => {
    ids.push(JSON.parse(options.body).thread_id);
    return new Promise((resolve, reject) => {
      options.signal.addEventListener("abort", () => reject(new Error("aborted")), { once: true });
    });
  };
  try {
    const running = render().send("问题");
    await render().send("不应重复发送");
    assert.equal(ids.length, 1);
    render().stop();
    await running;
    assert.equal(render().status, "ready");
    assert.equal(render().error, null);
    global.fetch = async (url, options) => {
      const id = JSON.parse(options.body).thread_id;
      ids.push(id);
      return new Response(sse([{ type: "done", thread_id: id }]));
    };
    await render().send("下一轮");
    assert.equal(ids[0], ids[1]);
  } finally { global.fetch = original; }
});
