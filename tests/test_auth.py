"""登录/会话/闸门（tasks 5.1–5.5、6.1、specs/user-auth）。"""

import pytest

from app.config import ConfigError, config_from_env

from .conftest import A1_PASS, TEACHER_PASS, auth_headers, login


def test_teacher_login_sets_session_and_role(client):
    resp = login(client, "teacher_a", TEACHER_PASS)
    assert resp.status_code == 200
    assert resp.get_json()["role"] == "teacher"
    set_cookie = " ".join(resp.headers.getlist("Set-Cookie"))
    assert "token=" in set_cookie
    # Cookie 属性：HttpOnly + SameSite=Lax（本机 HTTP 不设 Secure）
    assert "HttpOnly" in set_cookie
    assert "SameSite=Lax" in set_cookie

    # 下一受保护请求不再被重定向（携带 Authorization 头）
    me = client.get("/api/me", headers=auth_headers(resp))
    assert me.status_code == 200
    body = me.get_json()
    assert body["role"] == "teacher"
    assert set(body) == {"username", "role", "class_id"}


def test_student_login_success(client):
    resp = login(client, "student_a1", A1_PASS)
    assert resp.status_code == 200
    assert resp.get_json()["role"] == "student"


def test_wrong_credentials_401_without_session_and_generic_message(client):
    secret_typo = "definitely-wrong-pw-xyz"
    resp = login(client, "teacher_a", secret_typo)
    assert resp.status_code == 401
    assert resp.get_json() == {"error": "凭据无效"}
    assert not any("token=" in c for c in resp.headers.getlist("Set-Cookie"))
    # 明文口令不出现在错误响应中
    assert secret_typo not in resp.get_data(as_text=True)


def test_unknown_user_same_response_as_wrong_password(client):
    r1 = login(client, "no_such_user", "whatever")
    r2 = login(client, "teacher_a", "bad-pw")
    assert r1.status_code == r2.status_code == 401
    assert r1.get_json() == r2.get_json() == {"error": "凭据无效"}


def test_anonymous_page_redirects_to_login(client):
    resp = client.get("/materials", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/login")


def test_anonymous_api_401_without_protected_data(client):
    resp = client.get("/api/materials")
    assert resp.status_code == 401
    body = resp.get_data(as_text=True)
    assert "A班" not in body and "B班" not in body
    assert "教研" not in body and "stored_path" not in body


def test_logout_invalidates_old_cookie(client):
    resp = login(client, "teacher_a", TEACHER_PASS)
    headers = auth_headers(resp)
    assert client.get("/api/me", headers=headers).status_code == 200
    # 登出时携带 Authorization 头，让后端能拿到 jti 进行吊销
    assert client.post("/api/logout", headers=headers).status_code == 200
    # 旧 JWT 立即失效（jti 已入吊销清单），即便再带也拒绝
    assert client.get("/api/me", headers=headers).status_code == 401
    assert client.get("/materials", headers=headers).status_code == 302


def test_me_requires_auth(client):
    assert client.get("/api/me").status_code == 401


def test_health_is_public(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.get_json() == {"status": "ok"}


def test_missing_secret_key_refuses_startup(monkeypatch):
    for name in (
        "SECRET_KEY",
        "SEED_TEACHER_A_PASSWORD",
        "SEED_STUDENT_A1_PASSWORD",
        "SEED_STUDENT_B1_PASSWORD",
    ):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(ConfigError):
        config_from_env()
