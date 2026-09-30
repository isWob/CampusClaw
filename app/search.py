"""检索编排：keyword / vector / hybrid（RRF k=60）。

班级过滤双侧强制；跨班对外表现为无命中。
"""

import sqlite3

from flask import current_app

from .chunker import _bigram
from .db import get_db

NOT_FOUND_MSG = "资料中未找到相关内容"
RRF_K = 60


def keyword_search(query: str, class_id: int, db: sqlite3.Connection) -> list[dict]:
    """关键字检索：FTS5 MATCH + 班级过滤 + BM25 排序。不触嵌入与向量库。"""
    bigram_query = _bigram(query)
    if not bigram_query.strip():
        return []
    rows = db.execute(
        """
        SELECT c.id, c.material_id, c.class_id, c.chunk_index, c.chunk_text,
               c.char_start, c.char_end, m.filename AS material_title
        FROM chunks_fts f
        JOIN knowledge_chunks c ON c.id = f.chunk_id
        JOIN materials m ON m.id = c.material_id
        WHERE chunks_fts MATCH ? AND c.class_id = ?
        ORDER BY bm25(chunks_fts)
        LIMIT 20
        """,
        (bigram_query, class_id),
    ).fetchall()
    return [_hit_dict(r) for r in rows]


def vector_search(query: str, class_id: int, db: sqlite3.Connection) -> list[dict]:
    """向量检索：嵌入 → Qdrant 按班级过滤 → 余弦<0.35丢弃 → 回表取正文。"""
    from . import embedding, vector_store

    if not embedding.is_configured():
        return []  # 调用方据此返回 503

    vectors = embedding.embed([query])
    if not vectors:
        return []
    query_vec = vectors[0]

    results = vector_store.search_vectors(query_vec, class_id)
    hits = []
    for r in results:
        if r["score"] < vector_store.COSINE_THRESHOLD:
            continue
        chunk_id = r["chunk_id"]
        row = db.execute(
            """
            SELECT c.id, c.material_id, c.class_id, c.chunk_index, c.chunk_text,
                   c.char_start, c.char_end, m.filename AS material_title
            FROM knowledge_chunks c
            JOIN materials m ON m.id = c.material_id
            WHERE c.id = ? AND c.class_id = ?
            """,
            (chunk_id, class_id),
        ).fetchone()
        if row:
            hits.append({**_hit_dict(row), "score": r["score"]})
    return hits


def hybrid_search(query: str, class_id: int, db: sqlite3.Connection) -> list[dict]:
    """混合检索：两路各自过滤后按名次 RRF k=60 融合。"""
    kw = keyword_search(query, class_id, db)
    vec = vector_search(query, class_id, db)

    # RRF 融合
    scores: dict[int, float] = {}
    chunk_map: dict[int, dict] = {}

    for rank, hit in enumerate(kw):
        cid = hit["chunk_id"]
        scores[cid] = scores.get(cid, 0) + 1.0 / (RRF_K + rank + 1)
        chunk_map[cid] = hit
    for rank, hit in enumerate(vec):
        cid = hit["chunk_id"]
        scores[cid] = scores.get(cid, 0) + 1.0 / (RRF_K + rank + 1)
        chunk_map[cid] = hit

    ranked = sorted(scores.items(), key=lambda x: -x[1])
    return [{**chunk_map[cid], "rrf_score": score} for cid, score in ranked]


def _hit_dict(row) -> dict:
    return {
        "chunk_id": row["id"],
        "material_id": row["material_id"],
        "material_title": row["material_title"],
        "chunk_index": row["chunk_index"],
        "char_start": row["char_start"],
        "char_end": row["char_end"],
        "excerpt": row["chunk_text"][:200],
    }


def search(query: str, mode: str, class_id: int, db: sqlite3.Connection) -> list[dict]:
    """统一检索入口。"""
    if mode == "keyword":
        return keyword_search(query, class_id, db)
    elif mode == "vector":
        return vector_search(query, class_id, db)
    elif mode == "hybrid":
        return hybrid_search(query, class_id, db)
    raise ValueError(f"未知检索模式: {mode}")
