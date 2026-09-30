"""认证：登录/登出/当前会话身份（specs/user-auth）。

- POST /api/login   JSON 接口：成功 200 签发 JWT（Cookie + JSON），失败 401 统一文案；
- POST /login       登录页表单：成功 303 跳转材料页，失败 401 重渲染登录页；
- POST /api/logout、POST /logout：吊销 JWT + 清 Cookie；
- GET  /api/me      返回当前会话身份（供页面判定，授权仍只以服务端为准）。
"""

from flask import (
    Blueprint, current_app, g, jsonify, make_response, redirect,
    render_template, request, url_for,
)

from .. import repositories as repos
from ..db import get_db
from ..jwt_utils import sign_token, verify_token
from ..security import check_password
from ..tokens import revoke

bp = Blueprint("auth", __name__)

GENERIC_LOGIN_ERROR = "凭据无效"


def _authenticate(username: str, password: str):
    """凭据校验。用户不存在也做哑哈希比较，两条失败路径响应同形；不记明文。"""
    user = repos.get_user_by_username(get_db(), username)
    stored_hash = user["password_hash"] if user is not None else None
    if not check_password(password, stored_hash):
        return None
    return user


def _issue_token(user, app) -> str:
    """签发 JWT 并通过 Cookie 下发；返回 token 字符串。"""
    token = sign_token(user, app.config["SECRET_KEY"], app.config["JWT_EXPIRES"])
    return token


def _set_token_cookie(resp, token) -> None:
    """通过 HttpOnly Cookie 下发 JWT（供浏览器导航回退）。"""
    resp.set_cookie("token", token, httponly=True, samesite="Lax", path="/")


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
    token = _issue_token(user, current_app)
    resp = jsonify({**_identity(user), "token": token})
    _set_token_cookie(resp, token)
    return resp, 200


@bp.post("/api/logout")
def api_logout():
    """登出：吊销 JWT + 清 Cookie。"""
    auth_header = request.headers.get("Authorization", "")
    token = (
        auth_header[7:] if auth_header.startswith("Bearer ")
        else request.cookies.get("token")
    )
    if token:
        payload = verify_token(token, current_app.config["SECRET_KEY"])
        if payload:
            revoke(payload["jti"], payload["exp"])
    resp = jsonify({"status": "logged_out"})
    resp.delete_cookie("token", path="/")
    return resp, 200


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
    token = _issue_token(user, current_app)
    resp = make_response(redirect(url_for("pages.materials_page"), code=303))
    _set_token_cookie(resp, token)
    return resp


@bp.post("/logout")
def form_logout():
    token = request.cookies.get("token")
    if token:
        payload = verify_token(token, current_app.config["SECRET_KEY"])
        if payload:
            revoke(payload["jti"], payload["exp"])
    resp = make_response(redirect(url_for("pages.login_page"), code=303))
    resp.delete_cookie("token", path="/")
    return resp
