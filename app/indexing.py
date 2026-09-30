"""索引管道：切分 → 嵌入 → 向量库写入 + 关系库写入。"""

from flask import current_app

from . import embedding, vector_store
from .chunker import chunk, ChunkError
from .chunker import _bigram
from .db import get_db


def build_index(material_id: int, class_id: int, body_text: str,
                strategy: str = "auto", **kwargs) -> int:
    """为材料建立切片索引；返回切片数。"""
    db = get_db()
    # 先删旧切片
    _delete_chunks(db, material_id)

    chunks = chunk(body_text, strategy=strategy, **kwargs)
    if not chunks:
        return 0

    # 写关系库切片
    chunk_ids = []
    for i, c in enumerate(chunks):
        cur = db.execute(
            """INSERT INTO knowledge_chunks
               (material_id, class_id, chunk_index, chunk_text, char_start, char_end)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (material_id, class_id, i, c.text, c.char_start, c.char_end),
        )
        chunk_ids.append(int(cur.lastrowid))
        # 写 FTS5（2-gram）
        db.execute(
            "INSERT INTO chunks_fts (chunk_id, bigram_text) VALUES (?, ?)",
            (chunk_ids[-1], _bigram(c.text)),
        )
    db.commit()

    # 嵌入 + 向量库
    if embedding.is_configured():
        vectors = embedding.embed([c.text for c in chunks])
        if vectors:
            ready_ids = []
            payloads = []
            for cid, vec, c in zip(chunk_ids, vectors, chunks):
                payloads.append({
                    "class_id": class_id,
                    "material_id": material_id,
                    "chunk_id": cid,
                    "chunk_index": chunks.index(c),
                })
                ready_ids.append(cid)
            vector_store.upsert_points(ready_ids, vectors, payloads)
            # 标记嵌入成功
            db.execute(
                "UPDATE knowledge_chunks SET embed_status = 'ready' WHERE id IN ({})".format(
                    ",".join("?" * len(ready_ids))
                ),
                ready_ids,
            )
            db.commit()
        else:
            # 嵌入失败，标记 failed
            db.execute(
                "UPDATE knowledge_chunks SET embed_status = 'failed' WHERE material_id = ?",
                (material_id,),
            )
            db.commit()
    else:
        # 未配置嵌入，标记 failed（keyword 仍可用）
        db.execute(
            "UPDATE knowledge_chunks SET embed_status = 'failed' WHERE material_id = ?",
            (material_id,),
        )
        db.commit()

    return len(chunks)


def _delete_chunks(db, material_id: int):
    """删除材料的所有切片与 FTS 行。"""
    # 先取 chunk_ids
    rows = db.execute(
        "SELECT id FROM knowledge_chunks WHERE material_id = ?", (material_id,)
    ).fetchall()
    chunk_ids = [r["id"] for r in rows]
    # 删 FTS
    for cid in chunk_ids:
        db.execute("DELETE FROM chunks_fts WHERE chunk_id = ?", (cid,))
    # 删 chunks
    db.execute("DELETE FROM knowledge_chunks WHERE material_id = ?", (material_id,))
    db.commit()
    # 删向量库
    if chunk_ids:
        vector_store.delete_points(chunk_ids)


def reindex(material_id: int, class_id: int, body_text: str,
            strategy: str = "auto", **kwargs) -> int:
    """教师重建索引：删旧 → 重新写入。"""
    return build_index(material_id, class_id, body_text, strategy, **kwargs)
