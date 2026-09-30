"""CampusClaw 迭代 1：单一 Flask 应用工厂。

认证、授权、班级隔离全部在服务端强制执行：
- JWT 闸门（before_request）对每个受保护请求做完整校验（Complete Mediation）；
- 角色与班级每请求从用户表读取，不采信客户端回传的任何身份声明。
"""

from flask import Flask, g, jsonify, redirect, request, url_for

from . import repositories as repos
from .config import config_from_env
from .db import close_db, get_db
from .jwt_utils import verify_token
from .tokens import is_revoked

# 不入 JWT 闸门的白名单：健康检查与登录/登出本身
OPEN_PATHS = {"/health", "/login", "/api/login", "/logout", "/api/logout"}


def _extract_token(request) -> str | None:
    """从 Authorization: Bearer 头或 Cookie 中提取 JWT。"""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:]
    return request.cookies.get("token")


def create_app(overrides: dict | None = None) -> Flask:
    app = Flask(__name__)

    config = {} if overrides else config_from_env()
    config.update(overrides or {})
    app.config.update(
        SECRET_KEY=config["SECRET_KEY"],
        DATABASE_PATH=config["DATABASE_PATH"],
        UPLOAD_DIR=config["UPLOAD_DIR"],
        MAX_CONTENT_LENGTH=int(config["MAX_CONTENT_LENGTH"]),
        SEED_TEACHER_A_PASSWORD=config["SEED_TEACHER_A_PASSWORD"],
        SEED_STUDENT_A1_PASSWORD=config["SEED_STUDENT_A1_PASSWORD"],
        SEED_STUDENT_B1_PASSWORD=config["SEED_STUDENT_B1_PASSWORD"],
        JWT_EXPIRES=config.get("JWT_EXPIRES", 3600),
        QDRANT_URL=config.get("QDRANT_URL", ""),
        EMBEDDING_BASE_URL=config.get("EMBEDDING_BASE_URL", ""),
        EMBEDDING_API_KEY=config.get("EMBEDDING_API_KEY", ""),
        EMBEDDING_MODEL=config.get("EMBEDDING_MODEL", ""),
        CHAT_BASE_URL=config.get("CHAT_BASE_URL", ""),
        CHAT_API_KEY=config.get("CHAT_API_KEY", ""),
        CHAT_MODEL=config.get("CHAT_MODEL", ""),
        TUTOR_TOP_K=config.get("TUTOR_TOP_K", 4),
        TUTOR_MAX_HISTORY=config.get("TUTOR_MAX_HISTORY", 6),
    )

    app.teardown_appcontext(close_db)

    from .blueprints import auth, health, materials, pages, search, tutor

    app.register_blueprint(health.bp)
    app.register_blueprint(auth.bp)
    app.register_blueprint(materials.bp)
    app.register_blueprint(pages.bp)
    app.register_blueprint(search.bp)
    app.register_blueprint(tutor.bp)

    @app.before_request
    def jwt_gate():
        """JWT 验证闸门：验签 → 验吊销 → 回库查真实身份。"""
        g.current_user = None
        token = _extract_token(request)
        if token:
            payload = verify_token(token, app.config["SECRET_KEY"])
            if payload and not is_revoked(payload.get("jti", "")):
                user = repos.get_user_by_id(get_db(), payload["sub"])
                if user is not None:
                    g.current_user = user

        if request.path in OPEN_PATHS or request.path.startswith("/static"):
            return None

        if g.current_user is None:
            # 浏览器页面导航 → 302 登录页；API 调用 → 401 且不含任何业务数据
            if request.path.startswith("/api/"):
                return jsonify({"error": "需要认证"}), 401
            return redirect(url_for("pages.login_page"))
        return None

    @app.errorhandler(413)
    def payload_too_large(_exc):
        message = "文件超过大小上限"
        if request.path.startswith("/api/"):
            return jsonify({"error": message}), 413
        return message, 413

    return app
