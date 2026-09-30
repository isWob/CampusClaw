"""解题助手端点（specs/tutor-agent）。

- GET/PUT /api/tutor/prompt  教师读取/保存系统提示词（学生 403）
- GET/PUT /api/tutor/skill   教师读取/开关解题引导技能（学生 403）
- POST  /api/tutor/chat     SSE 流式会话（登录即可，班级取自会话）
"""

from flask import Blueprint, Response, current_app, g, jsonify, request, stream_with_context

from .. import tutor as tutor_mod
from ..db import get_db

bp = Blueprint("tutor", __name__)


def _teacher_only():
    """角色闸门：仅教师可操作，学生 403。返回 (None, None) 或 (error_resp, status)。"""
    if g.current_user["role"] != "teacher":
        return jsonify({"error": "仅教师可操作"}), 403
    return None


@bp.get("/api/tutor/prompt")
def get_prompt():
    err = _teacher_only()
    if err is not None:
        return err
    prompt_text, skill_enabled = tutor_mod.get_prompt_state(
        g.current_user["class_id"], get_db()
    )
    return jsonify({"prompt": prompt_text, "skill_enabled": bool(skill_enabled)}), 200


@bp.put("/api/tutor/prompt")
def put_prompt():
    err = _teacher_only()
    if err is not None:
        return err
    data = request.get_json(silent=True) or {}
    prompt_text = str(data.get("prompt", "")).strip()
    if not prompt_text:
        return jsonify({"error": "提示词不能为空"}), 400
    tutor_mod.save_prompt(
        g.current_user["class_id"], prompt_text, g.current_user["id"], get_db()
    )
    return jsonify({"status": "saved"}), 200


@bp.get("/api/tutor/skill")
def get_skill():
    err = _teacher_only()
    if err is not None:
        return err
    _, skill_enabled = tutor_mod.get_prompt_state(
        g.current_user["class_id"], get_db()
    )
    return jsonify({"skill_enabled": bool(skill_enabled)}), 200


@bp.put("/api/tutor/skill")
def put_skill():
    err = _teacher_only()
    if err is not None:
        return err
    data = request.get_json(silent=True) or {}
    if "skill_enabled" not in data:
        return jsonify({"error": "缺少 skill_enabled"}), 400
    enabled = bool(data["skill_enabled"])
    tutor_mod.save_skill(
        g.current_user["class_id"], enabled, g.current_user["id"], get_db()
    )
    return jsonify({"skill_enabled": enabled}), 200


@bp.post("/api/tutor/chat")
def chat():
    data = request.get_json(silent=True) or {}
    query = str(data.get("query", "")).strip()
    session_id = data.get("session_id")
    if session_id is not None:
        session_id = str(session_id).strip() or None

    if not query:
        return jsonify({"error": "查询不能为空"}), 400

    # 丢弃客户端注入的 system 消息（history 中不透传 system）
    history = data.get("history", [])
    if isinstance(history, list):
        history = [h for h in history if isinstance(h, dict) and h.get("role") != "system"]

    def generate():
        # 班级取自会话；客户端 history 仅作容错丢弃，真实历史从库取
        yield from tutor_mod.stream_tutor(
            query, session_id, g.current_user, get_db()
        )

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
