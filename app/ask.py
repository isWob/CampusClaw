"""问答编排：先检索后生成。

无命中不触网关；客户端 system 消息丢弃；[n] 标注与 citations 一致。
"""

import httpx
from flask import current_app

from . import search as search_mod
from .db import get_db

NOT_FOUND_MSG = "资料中未找到相关内容"


def ask(query: str, class_id: int, history: list[dict] | None = None,
        db=None) -> dict:
    """问答：混合检索取前 K → 有命中才调对话网关。"""
    if db is None:
        db = get_db()
    top_k = current_app.config.get("TUTOR_TOP_K", 4)
    max_history = current_app.config.get("TUTOR_MAX_HISTORY", 6)

    hits = search_mod.hybrid_search(query, class_id, db)[:top_k]
    if not hits:
        return {"answer": NOT_FOUND_MSG, "citations": []}

    # 组装上下文
    context = "\n\n".join(
        f"[{i+1}] {h['material_title']}（切片{h['chunk_index']}）：{h['excerpt']}"
        for i, h in enumerate(hits)
    )
    citations = [
        {"material_id": h["material_id"], "material_title": h["material_title"],
         "chunk_index": h["chunk_index"], "char_start": h["char_start"],
         "char_end": h["char_end"], "excerpt": h["excerpt"]}
        for i, h in enumerate(hits)
    ]

    # 检查对话网关
    chat_base = current_app.config.get("CHAT_BASE_URL", "")
    if not chat_base:
        return {"answer": "检索到相关内容，但对话服务未配置", "citations": citations}

    # 组装消息（客户端 system 丢弃，服务端组装自己的 system）
    system_prompt = (
        "你是教研助手。根据以下材料回答问题，"
        "在回答中用 [1]、[2] 等标注引用来源。"
        "如果材料中没有依据，请说明「资料中未找到相关内容」。\n\n"
        f"材料：\n{context}"
    )
    messages = [{"role": "system", "content": system_prompt}]
    # 历史轮次
    for h in (history or [])[-max_history:]:
        messages.append({"role": h.get("role", "user"), "content": h.get("content", "")})
    messages.append({"role": "user", "content": query})

    resp = httpx.post(
        f"{chat_base.rstrip('/')}/chat/completions",
        json={
            "model": current_app.config.get("CHAT_MODEL", ""),
            "messages": messages,
            "stream": False,
        },
        headers={"Authorization": f"Bearer {current_app.config.get('CHAT_API_KEY', '')}"},
        timeout=60.0,
    )
    resp.raise_for_status()
    answer = resp.json()["choices"][0]["message"]["content"]
    return {"answer": answer, "citations": citations}
