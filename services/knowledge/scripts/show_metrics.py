"""
把 /metrics 的 Prometheus 文本拉下来,转成人类友好的摘要(只显示有数据的指标)。

Prometheus 文本格式是给机器抓取用的,满屏 HELP/TYPE/全 0 的桶,人看很累。
这个脚本用官方 parser 解析后,只挑出"有数据"的指标:
  - counter   直接列每个 label 组合的数值
  - histogram 汇总成 次数 / 平均 / 累计(不展开一堆桶)

跑法(服务需在 127.0.0.1:8000 运行):
    python -m scripts.show_metrics
"""
from __future__ import annotations

import urllib.request

from prometheus_client.parser import text_string_to_metric_families

URL = "http://127.0.0.1:8000/metrics"


def render_metrics(text: str) -> str:
    """把 Prometheus 文本渲染成友好摘要字符串。纯函数,方便单测。"""
    lines: list[str] = []

    for fam in text_string_to_metric_families(text):
        if not fam.name.startswith("rag_"):
            continue

        if fam.type == "counter":
            rows = [
                (s.labels, s.value)
                for s in fam.samples
                if s.name.endswith("_total") and s.value > 0
            ]
            if rows:
                lines.append(f"\n■ {fam.documentation}")
                for labels, val in rows:
                    label_str = "  ".join(f"{k}={v}" for k, v in labels.items())
                    lines.append(f"    {label_str:<46} {int(val)}")

        elif fam.type == "histogram":
            # 把同一 label 组合的 _count / _sum 收到一起
            stats: dict[tuple, dict] = {}
            for s in fam.samples:
                if s.name.endswith("_count"):
                    stats.setdefault(tuple(sorted(s.labels.items())), {})["count"] = s.value
                elif s.name.endswith("_sum"):
                    stats.setdefault(tuple(sorted(s.labels.items())), {})["sum"] = s.value

            shown_header = False
            for key, st in stats.items():
                count = st.get("count", 0)
                if count <= 0:
                    continue
                if not shown_header:
                    lines.append(f"\n■ {fam.documentation}")
                    shown_header = True
                total = st.get("sum", 0.0)
                avg = total / count
                label_str = "  ".join(f"{k}={v}" for k, v in key) or "(无 label)"
                lines.append(
                    f"    {label_str:<46} 次数={int(count)}  平均={avg:.2f}  累计={total:.2f}"
                )

    if not lines:
        return "(还没有任何指标数据 —— 先发几个 /health 或 /query 请求)"
    return "\n".join(lines)


def main() -> None:
    try:
        text = urllib.request.urlopen(URL, timeout=5).read().decode()
    except Exception as e:  # noqa: BLE001 - 给用户一句人话提示就够
        print(f"拉取 {URL} 失败:{e}\n服务起了吗?先 `fastapi dev app/main.py`")
        return
    print(render_metrics(text))
    print()


if __name__ == "__main__":
    main()
