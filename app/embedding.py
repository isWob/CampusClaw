"""嵌入客户端：调用 OpenAI 兼容网关。

未配置时返回 None（降级模式）；调用方据此决定 keyword-only 或 503。
"""

import httpx
from flask import current_app


def is_configured() -> bool:
    return bool(current_app.config.get("EMBEDDING_BASE_URL")
                and current_app.config.get("EMBEDDING_MODEL"))


def embed(texts: list[str]) -> list[list[float]] | None:
    """批量嵌入；返回向量列表或 None（未配置）。"""
    if not is_configured():
        return None
    base = current_app.config["EMBEDDING_BASE_URL"].rstrip("/")
    resp = httpx.post(
        f"{base}/embeddings",
        json={
            "model": current_app.config["EMBEDDING_MODEL"],
            "input": texts,
        },
        headers={"Authorization": f"Bearer {current_app.config['EMBEDDING_API_KEY']}"}
            if current_app.config.get("EMBEDDING_API_KEY") else None,
        timeout=30.0,
    )
    resp.raise_for_status()
    data = resp.json()
    return [item["embedding"] for item in data["data"]]
