# AI 应用中的 SSE 流式链路笔记

这份文档关注 AI 应用从后端产生流式事件，到浏览器逐段读取，再更新 React 状态的完整链路。它适合测试 SSE、ReadableStream、TextDecoder、buffer、业务事件边界、AbortController 和流式错误处理等问题。

## 一条完整的 SSE 链路

在一个 AI 对话或 Agent 页面里，后端 service 可能持续产生不同语义事件，例如 `sources`、`token`、`step`、`done` 和 `error`。Router 再把这些业务事件编码成 SSE 文本，例如：

`data: {JSON}

`

如果前面还有 Next.js BFF，BFF 可以不解释每一种业务事件，而是尽量直接透传 response body。浏览器端通过 `fetch` 发起请求，再使用 `ReadableStream` 和 `TextDecoder` 持续读取网络字节。

## 网络 chunk 不等于业务事件

这是流式解析最重要的边界条件之一。一次 `reader.read()` 拿到的是网络传输层面的 chunk，它可能只包含半条 SSE，也可能一次带回来多条 SSE。网络如何分包和业务协议如何划分事件，没有一一对应关系。

因此不能对每一次 `reader.read()` 的结果直接 `JSON.parse()`。正确做法是：

1. `TextDecoder` 把字节转换成字符串。
2. 把新字符串追加到本地 buffer。
3. 按 SSE 事件分隔符，也就是双换行 `

`，不断拆出完整事件。
4. 对完整事件提取 `data:` 内容，再解析 JSON。
5. buffer 中剩下的不完整尾巴保留到下一次网络读取继续拼接。

这套逻辑的本质是：传输层 chunk 只是载体，真正应该解析的是协议层完整消息。

## 为什么要有语义事件

如果后端只不断返回纯文本 token，前端很难同时表达来源引用、工具调用步骤、完成状态和错误。更稳妥的设计是让流里包含明确事件类型，例如：

- `sources`：更新引用来源；
- `token`：追加回答正文；
- `step`：更新 Agent 工具步骤；
- `done`：标记正常完成；
- `error`：标记流式执行失败。

React 侧可以使用 reducer 按事件类型更新一条消息的结构化状态，而不是在每个 token 到达时到处拼接多个 state。

## AbortController 的作用

用户点击“停止生成”时，前端可以通过 `AbortController` 取消正在进行的 fetch。浏览器中止连接后，后端也应该尽量感知客户端断开，并停止继续调用模型、工具或下游服务，否则前端虽然不再接收，后端资源仍然在消耗。

这也是 AI 应用里成本控制的一部分：停止按钮不应该只是把 UI 状态改成停止，而要真正取消下游计算。

## 流开始后的错误怎么处理

在 HTTP 响应头还没有发送前，后端可以通过 4xx / 5xx 表示失败。但 SSE 一旦已经开始传输，HTTP 状态码通常已经确定，后续再发生模型异常或工具异常时，不能重新修改 HTTP 状态码。

因此流开始后的运行时错误，应该编码成业务层 `error` 事件发给前端。前端 reducer 接到后更新当前消息状态，例如保留已生成内容，同时标记失败原因和是否允许重试。

## 调试流式问题的顺序

如果页面出现 JSON 解析报错、文本缺字或多条消息粘连，先打印原始网络 chunk 和 buffer，再确认是否按 `

` 正确拆事件。如果停止按钮无效，检查 AbortSignal 是否真正传给 fetch，以及后端是否感知断开。如果流中途失败但页面一直 loading，检查后端是否发送了 `error` / `done` 事件，以及 reducer 是否在这些事件上结束 pending 状态。

最短版本可以记住：`fetch + ReadableStream + TextDecoder` 负责读流；buffer 负责解决网络 chunk 与业务事件边界不一致；按 `

` 拆出完整 SSE；reducer 按语义事件更新状态；用户停止用 AbortController；开流后的异常通过 `error` 事件返回。
