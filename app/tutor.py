"""解题助手编排器：提示词 + 解题引导技能 + 本班检索 → SSE 流式回答。

- 提示词与技能按班级生效，保存即写表，下一次 chat 请求读到新值（下一轮生效）。
- 每次提问：取会话历史 → hybrid 检索取前 K → 组装 system（教师提示词 + 技能约束 + 材料）
  → 丢弃客户端 system → 调对话网关 stream → SSE 逐段转发 → assistant 完整消息入库。
- 无命中返回固定文案 + 空 citations 不触网关；网关未配置时返回固定说明。
"""

import json
import uuid

import httpx
from flask import current_app

from . import search as search_mod
from .db import get_db

NOT_FOUND_MSG = "资料中未找到相关内容"
GATEWAY_UNCONFIGURED_MSG = "检索到相关内容，但对话服务未配置"

SKILL_ON_CONSTRAINT = (
    "你正在协助解题引导。只给解题思路，在回答中用 [1]、[2] 等引用本班材料的标题与位置，"
    "不要直接给出最终答案。"
)
SKILL_OFF_CONSTRAINT = "你可以直接给出问题的答案。"
CITATION_RULE = (
    "在回答中用 [1]、[2] 等标注引用来源。如果材料中没有依据，请说明「资料中未找到相关内容」。"
)
DEFAULT_PROMPT = "你是教研助手。请根据以下材料回答学生的问题。"


def get_prompt_state(class_id: int, db=None) -> tuple[str, int]:
    """读取本班当前提示词与技能开关。无行视为默认提示词与技能关闭。"""
    if db is None:
        db = get_db()
    row = db.execute(
        "SELECT prompt_text, skill_enabled FROM tutor_prompts WHERE class_id = ?",
        (class_id,),
    ).fetchone()
    if row is None:
        return DEFAULT_PROMPT, 0
    return row["prompt_text"] or DEFAULT_PROMPT, int(row["skill_enabled"])


def save_prompt(class_id: int, prompt_text: str, user_id: int, db=None) -> None:
    """保存提示词（UPSERT）；updated_by 取当前教师。"""
    if db is None:
        db = get_db()
    db.execute(
        "INSERT INTO tutor_prompts (class_id, prompt_text, skill_enabled, updated_by) "
        "VALUES (?, ?, COALESCE((SELECT skill_enabled FROM tutor_prompts WHERE class_id = ?), 0), ?) "
        "ON CONFLICT(class_id) DO UPDATE SET "
        "prompt_text = excluded.prompt_text, updated_at = datetime('now'), updated_by = excluded.updated_by",
        (class_id, prompt_text, class_id, user_id),
    )
    db.commit()


def save_skill(class_id: int, skill_enabled: bool, user_id: int, db=None) -> None:
    """开关解题引导技能（UPSERT）；保留既有提示词不变。"""
    if db is None:
        db = get_db()
    db.execute(
        "INSERT INTO tutor_prompts (class_id, prompt_text, skill_enabled, updated_by) "
        "VALUES (?, COALESCE((SELECT prompt_text FROM tutor_prompts WHERE class_id = ?), ''), ?, ?) "
        "ON CONFLICT(class_id) DO UPDATE SET "
        "skill_enabled = excluded.skill_enabled, updated_at = datetime('now'), updated_by = excluded.updated_by",
        (class_id, class_id, 1 if skill_enabled else 0, user_id),
    )
    db.commit()


def get_or_create_session(session_id: str | None, user_id: int, class_id: int,
                           db=None) -> tuple[str, bool]:
    """取会话；session_id 为空或不属于当前用户/班级 → 新建。返回 (session_id, created)。"""
    if db is None:
        db = get_db()
    if session_id:
        row = db.execute(
            "SELECT id FROM tutor_sessions WHERE id = ? AND user_id = ? AND class_id = ?",
            (session_id, user_id, class_id),
        ).fetchone()
        if row is not None:
            return row["id"], False
    new_id = uuid.uuid4().hex
    db.execute(
        "INSERT INTO tutor_sessions (id, user_id, class_id) VALUES (?, ?, ?)",
        (new_id, user_id, class_id),
    )
    db.commit()
    return new_id, True


def get_history(session_id: str, max_history: int, db=None) -> list[dict]:
    """取会话最近 N 轮（user/assistant 成对）作为网关上下文。"""
    if db is None:
        db = get_db()
    rows = db.execute(
        "SELECT role, content FROM tutor_messages WHERE session_id = ? "
        "ORDER BY seq DESC LIMIT ?",
        (session_id, max_history * 2),
    ).fetchall()
    # 反转为时间正序
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


def append_message(session_id: str, role: str, content: str, db=None) -> int:
    """追加消息；seq 会话内自增。返回 seq。"""
    if db is None:
        db = get_db()
    row = db.execute(
        "SELECT COALESCE(MAX(seq), 0) AS max_seq FROM tutor_messages WHERE session_id = ?",
        (session_id,),
    ).fetchone()
    seq = int(row["max_seq"]) + 1
    db.execute(
        "INSERT INTO tutor_messages (session_id, role, seq, content) VALUES (?, ?, ?, ?)",
        (session_id, role, seq, content),
    )
    db.commit()
    return seq


def _assemble_system(prompt_text: str, skill_enabled: int, hits: list[dict]) -> str:
    """组装 system：教师提示词 + 技能约束 + 材料 + 引用规则。三段同轮同时生效。"""
    parts = [prompt_text or DEFAULT_PROMPT]
    parts.append(SKILL_ON_CONSTRAINT if skill_enabled else SKILL_OFF_CONSTRAINT)
    context = "\n\n".join(
        f"[{i+1}] {h['material_title']}（切片{h['chunk_index']}）：{h['excerpt']}"
        for i, h in enumerate(hits)
    )
    parts.append(f"材料：\n{context}")
    parts.append(CITATION_RULE)
    return "\n\n".join(parts)


def _build_messages(system_prompt: str, query: str,
                    history: list[dict]) -> list[dict]:
    """组装网关消息：system + 历史 + 当前提问（客户端 system 已在端点丢弃）。"""
    messages = [{"role": "system", "content": system_prompt}]
    for h in history:
        messages.append({"role": h["role"], "content": h["content"]})
    messages.append({"role": "user", "content": query})
    return messages


def _sse(event: str, data: dict) -> str:
    """格式化一个 SSE 事件。"""
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"


def call_gateway_stream(messages: list[dict]) -> str:
    """调对话网关流式生成，逐段产出文本片段（生成器）。

    网关不可用或出错时抛异常，由调用方处理。
    """
    chat_base = current_app.config.get("CHAT_BASE_URL", "")
    with httpx.stream(
        "POST",
        f"{chat_base.rstrip('/')}/chat/completions",
        json={
            "model": current_app.config.get("CHAT_MODEL", ""),
            "messages": messages,
            "stream": True,
        },
        headers={"Authorization": f"Bearer {current_app.config.get('CHAT_API_KEY', '')}"},
        timeout=120.0,
    ) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines():
            if not line or not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if payload == "[DONE]":
                break
            try:
                chunk = json.loads(payload)
            except json.JSONDecodeError:
                continue
            choices = chunk.get("choices") or []
            if not choices:
                continue
            delta = choices[0].get("delta") or {}
            piece = delta.get("content") or ""
            if piece:
                yield piece


def stream_tutor(query: str, session_id: str | None, user, db=None):
    """生成器：产出 SSE 事件流。

    user 须为含 id/role/class_id 的 sqlite3.Row。
    """
    if db is None:
        db = get_db()
    class_id = user["class_id"]
    user_id = user["id"]
    top_k = current_app.config.get("TUTOR_TOP_K", 4)
    max_history = current_app.config.get("TUTOR_MAX_HISTORY", 6)

    # 1. 取/建会话
    sid, created = get_or_create_session(session_id, user_id, class_id, db)
    if created or session_id != sid:
        yield _sse("session", {"session_id": sid})

    # 2. 用户消息入库
    append_message(sid, "user", query, db)

    # 3. hybrid 检索取前 K
    hits = search_mod.hybrid_search(query, class_id, db)[:top_k]
    citations = [
        {"material_id": h["material_id"], "material_title": h["material_title"],
         "chunk_index": h["chunk_index"], "char_start": h["char_start"],
         "char_end": h["char_end"], "excerpt": h["excerpt"]}
        for h in hits
    ]

    # 4. 无命中：固定文案 + 空 citations 不触网关
    if not hits:
        yield _sse("citations", {"citations": []})
        yield _sse("delta", {"answer": NOT_FOUND_MSG})
        append_message(sid, "assistant", NOT_FOUND_MSG, db)
        yield _sse("done", {})
        return

    # 5. 先发 citations 事件
    yield _sse("citations", {"citations": citations})

    # 6. 检查对话网关
    chat_base = current_app.config.get("CHAT_BASE_URL", "")
    if not chat_base:
        # 有命中但网关未配置
        yield _sse("delta", {"answer": GATEWAY_UNCONFIGURED_MSG})
        append_message(sid, "assistant", GATEWAY_UNCONFIGURED_MSG, db)
        yield _sse("done", {})
        return

    # 7. 组装 system 与消息
    prompt_text, skill_enabled = get_prompt_state(class_id, db)
    system_prompt = _assemble_system(prompt_text, skill_enabled, hits)
    history = get_history(sid, max_history, db)
    # 历史中包含刚入库的当前 user 消息，需排除末尾的当前提问避免重复
    if history and history[-1]["role"] == "user" and history[-1]["content"] == query:
        history = history[:-1]
    messages = _build_messages(system_prompt, query, history)

    # 8. 调网关流式生成并逐段转发
    collected = []
    try:
        for piece in call_gateway_stream(messages):
            collected.append(piece)
            yield _sse("delta", {"answer": piece})
    except Exception as exc:
        err_msg = f"对话网关错误: {exc}"
        yield _sse("delta", {"answer": err_msg})
        collected.append(err_msg)

    full_answer = "".join(collected) or NOT_FOUND_MSG
    append_message(sid, "assistant", full_answer, db)
    yield _sse("done", {})
