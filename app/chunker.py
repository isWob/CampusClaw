"""正文切分器：三策略（auto/custom/hierarchy）。

偏移量相对输入文本；调用方负责将 body_text 传入，切片不改写原文。
"""

from dataclasses import dataclass


@dataclass
class Chunk:
    text: str
    char_start: int
    char_end: int


class ChunkError(Exception):
    """切分参数越界。"""
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


def _bigram(text: str) -> str:
    """将中文文本切为 2-gram 序列（空格连接），用于 FTS5 索引。"""
    chars = list(text.replace(" ", "").replace("\n", "").replace("\r", ""))
    if len(chars) < 2:
        return text
    return " ".join(a + b for a, b in zip(chars, chars[1:]))


def chunk_auto(text: str, max_len: int = 800, overlap: int = 80) -> list[Chunk]:
    """自动切分：≤max_len 字窗口、overlap 重叠、优先在空行/换行/句号断开。"""
    if not text:
        return []
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + max_len, len(text))
        if end < len(text):
            # 优先在空行、换行、句号断开
            for sep in ("\n\n", "\n", "。", "；", "；", ". ", "! ", "? "):
                cut = text.rfind(sep, start, end)
                if cut > start:
                    end = cut + len(sep)
                    break
        chunk_text = text[start:end]
        chunks.append(Chunk(text=chunk_text, char_start=start, char_end=end))
        if end >= len(text):
            break
        start = end - overlap if end - overlap > start else end
    return chunks


def chunk_custom(text: str, length: int = 800, overlap_pct: int = 10,
                 preprocess: bool = False) -> list[Chunk]:
    """自定义切分：长度 100–2000、重叠 0%–50%、可选预处理。"""
    if not (100 <= length <= 2000):
        raise ChunkError("切片长度须在 100–2000 字之间")
    if not (0 <= overlap_pct <= 50):
        raise ChunkError("重叠比例须在 0%–50% 之间")
    if not text:
        return []
    work = text
    if preprocess:
        import re
        work = re.sub(r"https?://\S+", "", work)
        work = re.sub(r"\S+@\S+", "", work)
        work = re.sub(r"\s+", " ", work)
    overlap = int(length * overlap_pct / 100)
    chunks = []
    start = 0
    while start < len(work):
        end = min(start + length, len(work))
        chunks.append(Chunk(text=work[start:end], char_start=start, char_end=end))
        if end >= len(work):
            break
        start = end - overlap if end - overlap > start else end
    return chunks


def chunk_hierarchy(text: str, max_len: int = 800, overlap: int = 80) -> list[Chunk]:
    """按 Markdown 标题分章：标题留章内，过长章按 auto 切。"""
    if not text:
        return []
    import re
    # 按 # / ## / ### 分章
    parts = re.split(r'(?=^#{1,3}\s)', text, flags=re.MULTILINE)
    chunks = []
    for part in parts:
        if not part.strip():
            continue
        if len(part) <= max_len:
            offset = text.index(part)
            chunks.append(Chunk(text=part, char_start=offset, char_end=offset + len(part)))
        else:
            # 过长章按 auto 切
            offset = text.index(part)
            sub = chunk_auto(part, max_len, overlap)
            for c in sub:
                chunks.append(Chunk(text=c.text, char_start=offset + c.char_start,
                                    char_end=offset + c.char_end))
    return chunks


def chunk(text: str, strategy: str = "auto", **kwargs) -> list[Chunk]:
    """按策略切分。"""
    if strategy == "auto":
        return chunk_auto(text, **kwargs)
    elif strategy == "custom":
        return chunk_custom(text, **kwargs)
    elif strategy == "hierarchy":
        return chunk_hierarchy(text, **kwargs)
    raise ChunkError(f"未知切分策略: {strategy}")
