// rehype 插件:把答案正文里的 [n] 标记(且 n 是有效来源编号)替换成可点击的 <cite data-ref="n"> 元素。
// 手写递归遍历 hast(不引 unist-util-visit),只动 text 节点,跳过代码块里的 [n]。

interface HastNode {
  type: string;
  tagName?: string;
  value?: string;
  properties?: Record<string, unknown>;
  children?: HastNode[];
}

const CITE_RE = /\[(\d+)\]/g;

// 代码块/行内代码里的 [n] 不当引用处理
const SKIP_TAGS = new Set(["code", "pre"]);

export function rehypeCitations({ validIds }: { validIds: Set<number> }) {
  return (tree: HastNode) => {
    if (validIds.size === 0) return; // 没来源(如 agent 模式)就不动
    walk(tree, validIds);
  };
}

function walk(node: HastNode, validIds: Set<number>) {
  if (!node.children || node.children.length === 0) return;
  if (node.tagName && SKIP_TAGS.has(node.tagName)) return;

  const next: HastNode[] = [];
  for (const child of node.children) {
    if (child.type === "text" && child.value && CITE_RE.test(child.value)) {
      next.push(...splitText(child.value, validIds));
    } else {
      walk(child, validIds);
      next.push(child);
    }
  }
  node.children = next;
}

function splitText(value: string, validIds: Set<number>): HastNode[] {
  const parts: HastNode[] = [];
  let last = 0;
  CITE_RE.lastIndex = 0;
  let m: RegExpExecArray | null;
  while ((m = CITE_RE.exec(value)) !== null) {
    const n = Number(m[1]);
    if (!validIds.has(n)) continue; // 无效编号:留在原文本里,不变成引用
    if (m.index > last) parts.push({ type: "text", value: value.slice(last, m.index) });
    parts.push({
      type: "element",
      tagName: "cite",
      properties: { dataRef: n, className: ["cite-ref"] },
      children: [{ type: "text", value: String(n) }],
    });
    last = m.index + m[0].length;
  }
  if (last < value.length) parts.push({ type: "text", value: value.slice(last) });
  return parts.length > 0 ? parts : [{ type: "text", value }];
}
