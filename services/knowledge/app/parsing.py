"""
文件解析层:把不同格式的文件统一解析为纯文本。
"""
from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)


# ---------- PDF 解析 ----------

def parse_pdf(data: bytes) -> str:
    """解析 PDF bytes → 纯文本字符串。

    - 用 PyMuPDF 提取每页文本
    - 自动按"块"分段(PyMuPDF 内置启发式)
    - 用 \\n\\n 分隔每页,让 chunker 看到段落边界
    - 简单清理重复页眉页脚
    """
    import fitz   # PyMuPDF 的 import 名是 fitz

    doc = fitz.open(stream=data, filetype="pdf")
    try:
        pages_text: list[str] = []
        for page in doc:
            # "blocks" 模式比 "text" 更尊重原文段落结构
            text = page.get_text("text")
            text = _clean_page_text(text)
            if text.strip():
                pages_text.append(text)
    finally:
        doc.close()

    full_text = "\n\n".join(pages_text)
    full_text = _remove_repeated_headers_footers(full_text)
    return full_text


def _clean_page_text(text: str) -> str:
    """单页文本的基本清理。"""
    # 去掉行尾多余空格
    text = re.sub(r"[ \t]+\n", "\n", text)
    # 多个连续换行压缩成最多 2 个
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _remove_repeated_headers_footers(text: str) -> str:
    """启发式:每页都重复出现的短行(<=50 字符)很可能是页眉页脚,删掉。"""
    pages = text.split("\n\n")
    if len(pages) < 3:
        return text   # 页数太少,启发式不可靠

    # 统计每行出现频率
    from collections import Counter
    line_counts: Counter[str] = Counter()
    for page in pages:
        for line in page.split("\n"):
            line = line.strip()
            if 0 < len(line) <= 50:
                line_counts[line] += 1

    # 出现在 ≥ 80% 页面的短行视为页眉页脚
    threshold = max(2, int(len(pages) * 0.8))
    boilerplate = {line for line, count in line_counts.items() if count >= threshold}

    if not boilerplate:
        return text

    logger.info("removed %d boilerplate lines", len(boilerplate))

    cleaned_pages = []
    for page in pages:
        cleaned_lines = [
            line for line in page.split("\n")
            if line.strip() not in boilerplate
        ]
        cleaned_pages.append("\n".join(cleaned_lines))
    return "\n\n".join(cleaned_pages)


# ---------- 统一调度 ----------

def parse_file(data: bytes, content_type: str, filename: str) -> str:
    """根据 content_type / filename 派发到对应 parser。"""
    name_lower = filename.lower()

    if name_lower.endswith(".pdf") or content_type == "application/pdf":
        return parse_pdf(data)

    # 其他类型走简单解码
    return _decode_text(data)


def _decode_text(data: bytes) -> str:
    """文本类文件(txt/md)的解码,从 upload 路由搬过来。"""
    for encoding in ("utf-8", "utf-8-sig", "gbk"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("Cannot decode file: unsupported encoding (tried utf-8, gbk)")