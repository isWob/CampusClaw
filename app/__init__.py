"""CampusClaw 迭代 1：单一 Flask 应用工厂。

认证、授权、班级隔离全部在服务端强制执行：
- 会话闸门（before_request）对每个受保护请求做完整校验（Complete Mediation）；
- 角色与班级每请求从用户表读取，不采信客户端回传的任何身份声明。
"""

from flask import Flask, g, jsonify, redirect, request, session, url_for

from . import repositories as repos
from .config import config_from_env
from .db import close_db, get_db

# 不入会话闸门的白名单：健康检查与登录/登出本身
OPEN_PATHS = {"/health", "/login", "/api/login", "/logout", "/api/logout"}


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
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",  # 同源站点；本机 HTTP 不设 Secure
    )

    app.teardown_appcontext(close_db)

    from .blueprints import auth, health, materials, pages

    app.register_blueprint(health.bp)
    app.register_blueprint(auth.bp)
    app.register_blueprint(materials.bp)
    app.register_blueprint(pages.bp)

    @app.before_request
    def session_gate():
        """每个请求的认证闸门 + 从库恢复身份（默认拒绝，白名单除外）。"""
        g.current_user = None
        if session.get("user_id"):
            user = repos.get_user_by_id(get_db(), session["user_id"])
            if user is not None:
                g.current_user = user
            else:
                # 会话指向已不存在的账号，作废该会话
                session.clear()

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
