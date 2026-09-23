"""健康存活端点（无需认证，在会话闸门白名单中）。"""

from flask import Blueprint, jsonify

bp = Blueprint("health", __name__)


@bp.get("/health")
def health():
    return jsonify({"status": "ok"}), 200
