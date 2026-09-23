"""认证：登录/登出/当前会话身份（specs/user-auth）。

- POST /api/login   JSON 接口：成功 200 设会话，失败 401 统一文案；
- POST /login       登录页表单：成功 303 跳转材料页，失败 401 重渲染登录页；
- POST /api/logout、POST /logout：清除会话；
- GET  /api/me      返回当前会话身份（供页面判定，授权仍只以服务端为准）。
"""

from flask import (
    Blueprint, g, jsonify, redirect, render_template, request, session, url_for,
)

from .. import repositories as repos
from ..db import get_db
from ..security import check_password

bp = Blueprint("auth", __name__)

GENERIC_LOGIN_ERROR = "凭据无效"


def _authenticate(username: str, password: str):
    """凭据校验。用户不存在也做哑哈希比较，两条失败路径响应同形；不记明文。"""
    user = repos.get_user_by_username(get_db(), username)
    stored_hash = user["password_hash"] if user is not None else None
    if not check_password(password, stored_hash):
        return None
    return user


def _start_session(user) -> None:
    """登录成功先清空旧会话再写入（防会话固定），会话不存密码。"""
    session.clear()
    session["user_id"] = user["id"]
    session["username"] = user["username"]
    session["role"] = user["role"]
    session["class_id"] = user["class_id"]


def _identity(user) -> dict:
    return {
        "username": user["username"],
        "role": user["role"],
        "class_id": user["class_id"],
    }


@bp.post("/api/login")
def api_login():
    data = request.get_json(silent=True) or {}
    username = str(data.get("username", ""))
    password = str(data.get("password", ""))
    user = _authenticate(username, password)
    if user is None:
        return jsonify({"error": GENERIC_LOGIN_ERROR}), 401
    _start_session(user)
    return jsonify(_identity(user)), 200


@bp.post("/api/logout")
def api_logout():
    session.clear()
    return jsonify({"status": "logged_out"}), 200


@bp.get("/api/me")
def api_me():
    return jsonify(_identity(g.current_user)), 200


@bp.post("/login")
def form_login():
    username = request.form.get("username", "")
    password = request.form.get("password", "")
    user = _authenticate(username, password)
    if user is None:
        # 统一文案，不区分用户名不存在/密码错误
        return render_template(
            "login.html", error=GENERIC_LOGIN_ERROR, username=username
        ), 401
    _start_session(user)
    return redirect(url_for("pages.materials_page"), code=303)


@bp.post("/logout")
def form_logout():
    session.clear()
    return redirect(url_for("pages.login_page"), code=303)
