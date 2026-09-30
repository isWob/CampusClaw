"""知识库检索与问答端点。

- POST /api/search   检索本班知识库
- POST /api/ask      先检索后生成问答
- POST /api/materials/<id>/reindex  教师重建索引
"""

from flask import Blueprint, current_app, g, jsonify, request

from .. import search as search_mod
from ..db import get_db
from ..indexing import reindex, ChunkError

bp = Blueprint("search", __name__)

NOT_FOUND_MSG = "资料中未找到相关内容"


@bp.post("/api/search")
def search():
    data = request.get_json(silent=True) or {}
    query = str(data.get("query", "")).strip()
    mode = str(data.get("mode", "hybrid")).strip()

    if not query:
        return jsonify({"error": "查询不能为空"}), 400

    if mode not in ("keyword", "vector", "hybrid"):
        return jsonify({"error": "未知检索模式"}), 400

    class_id = g.current_user["class_id"]

    if mode in ("vector", "hybrid"):
        from .. import embedding
        if not embedding.is_configured():
            return jsonify({"error": "向量检索服务不可用"}), 503

    hits = search_mod.search(query, mode, class_id, get_db())
    return jsonify({
        "hits": hits,
        "message": "" if hits else NOT_FOUND_MSG,
    }), 200


@bp.post("/api/ask")
def ask():
    data = request.get_json(silent=True) or {}
    query = str(data.get("query", "")).strip()
    history = data.get("history", [])

    if not query:
        return jsonify({"error": "查询不能为空"}), 400

    # 丢弃客户端注入的 system 消息
    if isinstance(history, list):
        history = [h for h in history if isinstance(h, dict) and h.get("role") != "system"]

    from .. import ask as ask_mod
    result = ask_mod.ask(query, g.current_user["class_id"], history, get_db())
    return jsonify(result), 200


@bp.post("/api/materials/<int:material_id>/reindex")
def reindex_material(material_id: int):
    if g.current_user["role"] != "teacher":
        return jsonify({"error": "仅教师可重建索引"}), 403

    from .. import repositories as repos
    row = repos.get_material_by_id(get_db(), material_id)
    if row is None or row["class_id"] != g.current_user["class_id"]:
        return jsonify({"error": "材料不存在"}), 404

    data = request.get_json(silent=True) or {}
    strategy = str(data.get("strategy", "auto"))

    # 取 body_text
    mat = get_db().execute(
        "SELECT body_text FROM materials WHERE id = ?", (material_id,)
    ).fetchone()
    if not mat or not mat["body_text"]:
        return jsonify({"error": "材料无正文"}), 400

    # 收集切分参数（按策略透传）
    kwargs = {}
    if strategy == "auto":
        if "max_len" in data:
            kwargs["max_len"] = int(data["max_len"])
        if "overlap" in data:
            kwargs["overlap"] = int(data["overlap"])
    elif strategy == "custom":
        if "length" in data:
            kwargs["length"] = int(data["length"])
        if "overlap_pct" in data:
            kwargs["overlap_pct"] = int(data["overlap_pct"])
        if "preprocess" in data:
            kwargs["preprocess"] = bool(data["preprocess"])
    elif strategy == "hierarchy":
        if "max_len" in data:
            kwargs["max_len"] = int(data["max_len"])
        if "overlap" in data:
            kwargs["overlap"] = int(data["overlap"])

    try:
        count = reindex(material_id, g.current_user["class_id"],
                        mat["body_text"], strategy, **kwargs)
    except ChunkError as exc:
        return jsonify({"error": exc.message}), exc.status
    except (TypeError, ValueError) as exc:
        return jsonify({"error": f"参数错误: {exc}"}), 400

    return jsonify({"chunks": count}), 200
