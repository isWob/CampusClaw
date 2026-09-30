"""向量库客户端：Qdrant 封装。

未配置时返回 None（降级模式）。
"""

from flask import current_app

COLLECTION = "campusclaw_chunks"
COSINE_THRESHOLD = 0.35


def _get_client():
    url = current_app.config.get("QDRANT_URL", "")
    if not url:
        return None
    from qdrant_client import QdrantClient
    return QdrantClient(url=url, timeout=10.0)


def _existing_vector_size(client) -> int | None:
    """探测既有集合的向量维度；不存在或无法判定返回 None。"""
    try:
        info = client.get_collection(COLLECTION)
    except Exception:
        return None
    params = info.config.params.vectors
    # 单向量配置：VectorParams 对象或 dict
    size = getattr(params, "size", None)
    if size is None and isinstance(params, dict):
        size = params.get("size")
    return int(size) if size else None


def _ensure_collection(client, dim: int) -> None:
    """确保集合存在且维度为 dim；维度不匹配则重建。"""
    existing = _existing_vector_size(client)
    if existing is None:
        from qdrant_client.models import Distance, VectorParams
        client.create_collection(
            COLLECTION,
            vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
        )
        return
    if existing != dim:
        client.delete_collection(COLLECTION)
        from qdrant_client.models import Distance, VectorParams
        client.create_collection(
            COLLECTION,
            vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
        )


def ensure_collection():
    """启动时探活；实际集合按首次 upsert 的向量维度创建。"""
    client = _get_client()
    if client is None:
        return
    try:
        client.get_collection(COLLECTION)
    except Exception:
        pass  # 不预先用占位维度创建，避免与真实维度不匹配


def upsert_points(chunk_ids: list[int], vectors: list[list[float]],
                  payloads: list[dict]):
    """批量写入向量与 payload。"""
    client = _get_client()
    if client is None:
        return
    if not vectors:
        return
    from qdrant_client.models import PointStruct
    dim = len(vectors[0])
    _ensure_collection(client, dim)
    points = [
        PointStruct(id=cid, vector=vec, payload=p)
        for cid, vec, p in zip(chunk_ids, vectors, payloads)
    ]
    client.upsert(COLLECTION, points=points)


def delete_points(chunk_ids: list[int]):
    """按 chunk_id 删除向量。"""
    client = _get_client()
    if client is None:
        return
    from qdrant_client.models import PointIdsList
    try:
        client.delete(collection_name=COLLECTION,
                      points_selector=PointIdsList(points=chunk_ids))
    except Exception:
        pass


def search_vectors(query_vector: list[float], class_id: int,
                   top_k: int = 20) -> list[dict]:
    """按班级过滤搜索向量；返回 [{chunk_id, score, payload}]。"""
    client = _get_client()
    if client is None:
        return []
    from qdrant_client.models import FieldCondition, MatchValue, Filter
    # 新版 qdrant_client 用 query_points 替代已废弃的 search
    results = client.query_points(
        collection_name=COLLECTION,
        query=query_vector,
        query_filter=Filter(
            must=[FieldCondition(key="class_id", match=MatchValue(value=class_id))]
        ),
        limit=top_k,
        with_payload=True,
    ).points
    return [
        {"chunk_id": r.payload.get("chunk_id"),
         "score": r.score,
         "payload": r.payload}
        for r in results
    ]
