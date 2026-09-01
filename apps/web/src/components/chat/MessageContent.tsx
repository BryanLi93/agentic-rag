import { Markdown } from "./Markdown";

// 助手消息正文统一走 Markdown 渲染(D5/D6),并把引用联动透传给 Markdown(W12-D2)。
export function MessageContent({
  text,
  validIds,
  onCite,
}: {
  text: string;
  validIds?: Set<number>;
  onCite?: (n: number) => void;
}) {
  return <Markdown text={text} validIds={validIds} onCite={onCite} />;
}
