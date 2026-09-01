"""
文本分块模块。

策略:递归字符切分,优先按段落/句子/标点切,避免切断完整语义。
中英混合友好。
"""

from __future__ import annotations

from dataclasses import dataclass

import tiktoken
from langchain_text_splitters import RecursiveCharacterTextSplitter

# ---------- 常量 ----------

# chunk_size 单位是字符数,不是 token 数
# 中文一个字 ~1.5 token,英文 ~0.25 token,500 字符大约 100-700 tokens
# 起步值偏保守,远低于 bge-m3 的 8192 token 上限
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50

# 分隔符顺序:从粗到细,优先在更"自然"的位置切
# 中英混合:中文句末标点 + 英文句末标点 + 通用空白
SEPARATORS = [
    "\n\n",     # 段落
    "\n",       # 行
    "。", "？", "！",        # 中文句末
    ". ", "? ", "! ",       # 英文句末(带空格避免切坏小数)
    ";", "；",  # 分号
    ",", ",",   # 逗号(最后兜底)
    " ",        # 空格
    "",         # 字符级(穷尽兜底)
]

# ---------- 数据结构 ----------

@dataclass
class Chunk:
    """单个分块结果。"""
    index: int # 在原文档中的顺序(从 0 开始)
    content: str # chunk 文本
    token_count: int # 估算的 token 数(用于监控)

# ---------- 工具函数 ----------

_encoder = tiktoken.get_encoding("cl100k_base")

def estimate_tokens(text: str) -> int:
    """估算 token 数。用 cl100k_base 编码,对 Qwen3.5 / bge-m3 来说是近似值。"""
    return len(_encoder.encode(text))

# ---------- 核心 API ----------
def split_text(
    text: str,
    chunk_size: int = CHUNK_SIZE,
    chunk_overlap: int = CHUNK_OVERLAP
) -> list[Chunk]:
    """
    把长文本切成 chunks。

    Args:
        text: 待切分的文本
        chunk_size: 每个 chunk 的最大字符数
        chunk_overlap: 相邻 chunk 之间重叠的字符数(防止边界处语义被切断)

    Returns:
        Chunk 列表,顺序与原文一致。空文本返回空列表。
    """
    if not text or not text.strip():
        return []

    """
    RecursiveCharacterTextSplitter 的核心逻辑：
        1. 用 SEPARATORS[0] (段落 \n\n) 切文本 → 得到一组段落
        2. 对每个段落:
            - 如果 ≤ chunk_size,保留
            - 如果 > chunk_size,递归用 SEPARATORS[1] 再切
        3. 直到所有片段都 ≤ chunk_size
        4. 合并相邻小片段,直到接近 chunk_size 但不超过
        5. *添加 overlap
            - Overlap 只在 splitter 必须把单个超长段落切碎时才会被加入。当所有原始段落都小于 chunk_size 时，splitter 走的是纯合并路径，相邻 chunk 之间没有 overlap。
    """

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=SEPARATORS,
        length_function=len, # 用字符数衡量长度
        is_separator_regex=False,
        keep_separator=True, # 保留分隔符,不丢失标点
    )

    raw_chunks = splitter.split_text(text)

    return [
        Chunk(
            index=i,
            content=chunk,
            token_count=estimate_tokens(chunk)
        )
        for i, chunk in enumerate(raw_chunks)
    ]