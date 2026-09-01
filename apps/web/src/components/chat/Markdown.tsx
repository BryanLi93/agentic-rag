import { createContext, memo, useContext } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import { rehypeCitations } from "@/lib/rehype-citations";

// 引用点击回调通过 context 传给 module 级的 cite 组件,避免每条消息重建 components。
const CitationContext = createContext<{ onCite: (n: number) => void } | null>(
  null,
);

// 单独的大写组件承载 useContext(满足 rules-of-hooks);cite renderer 只做转发。
function CiteRef({
  refNum,
  children,
}: {
  refNum: number;
  children: React.ReactNode;
}) {
  const ctx = useContext(CitationContext);
  return (
    <button
      type="button"
      onClick={() => ctx?.onCite(refNum)}
      className="cite-ref mx-px cursor-pointer align-super text-[0.72em] font-semibold text-blue-600 not-italic hover:underline dark:text-blue-400"
    >
      [{children}]
    </button>
  );
}

// 元素级样式覆盖(不引 typography 插件,裸写以便完全控制代码块与高亮的配合)。
const components: Components = {
  p: ({ children }) => (
    <p className="my-2 leading-relaxed first:mt-0 last:mb-0">{children}</p>
  ),
  ul: ({ children }) => (
    <ul className="my-2 list-disc space-y-1 pl-5">{children}</ul>
  ),
  ol: ({ children }) => (
    <ol className="my-2 list-decimal space-y-1 pl-5">{children}</ol>
  ),
  h1: ({ children }) => (
    <h1 className="my-3 text-lg font-semibold first:mt-0">{children}</h1>
  ),
  h2: ({ children }) => (
    <h2 className="my-3 text-base font-semibold first:mt-0">{children}</h2>
  ),
  h3: ({ children }) => (
    <h3 className="my-2 text-sm font-semibold first:mt-0">{children}</h3>
  ),
  a: ({ children, href }) => (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="text-blue-600 underline underline-offset-2 dark:text-blue-400"
    >
      {children}
    </a>
  ),
  blockquote: ({ children }) => (
    <blockquote className="my-2 border-l-2 border-black/20 pl-3 text-zinc-500 dark:border-white/20">
      {children}
    </blockquote>
  ),
  hr: () => <hr className="my-3 border-black/10 dark:border-white/10" />,
  table: ({ children }) => (
    <div className="my-2 overflow-x-auto">
      <table className="w-full border-collapse text-xs">{children}</table>
    </div>
  ),
  th: ({ children }) => (
    <th className="border border-black/25 bg-black/10 px-2 py-1 text-left font-semibold dark:border-white/25 dark:bg-white/15">
      {children}
    </th>
  ),
  td: ({ children }) => (
    <td className="border border-black/25 px-2 py-1 dark:border-white/25">
      {children}
    </td>
  ),
  // 由 rehypeCitations 生成的 <cite data-ref="n">:转发给 CiteRef 渲染成可点击角标。
  cite: ({ node, children }) => (
    <CiteRef
      refNum={Number((node?.properties as { dataRef?: number })?.dataRef)}
    >
      {children}
    </CiteRef>
  ),
  // rehype-highlight 在进入组件前已给「代码块」打上 `language-x hljs` 类并切好高亮 span;
  // 这里只区分行内 code(无 language)与块级 code(保留 hljs 类,样式见 globals.css)。
  code: ({ className, children, ...props }) => {
    const isBlock = /language-/.test(className ?? "");
    if (isBlock) {
      return (
        <code className={className} {...props}>
          {children}
        </code>
      );
    }
    return (
      <code
        className="rounded bg-black/10 px-1 py-0.5 text-[0.85em] dark:bg-white/15"
        {...props}
      >
        {children}
      </code>
    );
  },
};

/**
 * 流式 Markdown 渲染。靠 memo(text 不变就不重渲)兜逐 token 重渲染的开销。
 * 流式渲染使用同步的 rehype-highlight,避免异步高亮阻塞 token 更新。
 */
export const Markdown = memo(function Markdown({
  text,
  validIds,
  onCite,
}: {
  text: string;
  validIds?: Set<number>; // 有效来源编号;给了才把 [n] 变可点击
  onCite?: (n: number) => void;
}) {
  const ids = validIds ?? EMPTY_IDS;
  return (
    <CitationContext.Provider value={onCite ? { onCite } : null}>
      <div className="text-sm">
        <ReactMarkdown
          components={components}
          remarkPlugins={[remarkGfm]}
          rehypePlugins={[
            [rehypeCitations, { validIds: ids }],
            [rehypeHighlight, { detect: true, ignoreMissing: true }],
          ]}
        >
          {text}
        </ReactMarkdown>
      </div>
    </CitationContext.Provider>
  );
});

const EMPTY_IDS: Set<number> = new Set();
