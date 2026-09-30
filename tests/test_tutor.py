"""解题助手测试：提示词、技能、SSE 会话。"""

import json
from io import BytesIO
from unittest.mock import MagicMock, patch

from .conftest import A1_PASS, TEACHER_PASS, auth_headers, login


def _upload_material(client, headers, content: str, filename="lesson.txt"):
    """教师上传一份有内容的材料。"""
    client.post("/api/materials",
        data={"file": (BytesIO(content.encode("utf-8")), filename)},
        content_type="multipart/form-data",
        headers=headers)


def _patch_gateway(pieces: list[str]):
    """patch app.tutor.call_gateway_stream 为返回 pieces 的生成器。

    返回 (patcher, captured) 其中 captured["messages"] 在调用后被填充。
    """
    captured = {"messages": None}

    def _fake_generator(messages):
        captured["messages"] = messages
        for p in pieces:
            yield p

    return patch("app.tutor.call_gateway_stream", _fake_generator), captured


# ── 提示词端点 ─────────────────────────────────────────────────
def test_prompt_student_forbidden(client):
    """学生不可读取/修改提示词。"""
    resp = login(client, "student_a1", A1_PASS)
    headers = auth_headers(resp)
    assert client.get("/api/tutor/prompt", headers=headers).status_code == 403
    assert client.put("/api/tutor/prompt",
        json={"prompt": "x"}, headers=headers).status_code == 403


def test_prompt_unauthenticated_rejected(client):
    """未登录调用提示词端点 401。"""
    assert client.get("/api/tutor/prompt").status_code == 401
    assert client.put("/api/tutor/prompt",
        json={"prompt": "x"}).status_code == 401


def test_prompt_teacher_save_and_read(client):
    """教师保存提示词后可读回。"""
    resp = login(client, "teacher_a", TEACHER_PASS)
    headers = auth_headers(resp)
    data = client.get("/api/tutor/prompt", headers=headers).get_json()
    assert data["skill_enabled"] is False

    r = client.put("/api/tutor/prompt",
        json={"prompt": "你是数学解题助手"}, headers=headers)
    assert r.status_code == 200

    data = client.get("/api/tutor/prompt", headers=headers).get_json()
    assert data["prompt"] == "你是数学解题助手"


def test_prompt_empty_rejected(client):
    """空提示词 400。"""
    resp = login(client, "teacher_a", TEACHER_PASS)
    headers = auth_headers(resp)
    assert client.put("/api/tutor/prompt",
        json={"prompt": ""}, headers=headers).status_code == 400


# ── 技能端点 ─────────────────────────────────────────────────
def test_skill_student_forbidden(client):
    """学生不可开关技能。"""
    resp = login(client, "student_a1", A1_PASS)
    headers = auth_headers(resp)
    assert client.get("/api/tutor/skill", headers=headers).status_code == 403
    assert client.put("/api/tutor/skill",
        json={"skill_enabled": True}, headers=headers).status_code == 403


def test_skill_teacher_toggle(client):
    """教师开关技能。"""
    resp = login(client, "teacher_a", TEACHER_PASS)
    headers = auth_headers(resp)
    r = client.put("/api/tutor/skill",
        json={"skill_enabled": True}, headers=headers)
    assert r.status_code == 200
    assert r.get_json()["skill_enabled"] is True
    assert client.get("/api/tutor/skill", headers=headers).get_json()["skill_enabled"] is True

    client.put("/api/tutor/skill",
        json={"skill_enabled": False}, headers=headers)
    assert client.get("/api/tutor/skill", headers=headers).get_json()["skill_enabled"] is False


# ── chat 端点 ─────────────────────────────────────────────────
def test_chat_empty_query_rejected(client):
    """空查询 400。"""
    resp = login(client, "student_a1", A1_PASS)
    headers = auth_headers(resp)
    assert client.post("/api/tutor/chat",
        json={"query": ""}, headers=headers).status_code == 400


def test_chat_no_hit_returns_fixed_message(client):
    """无命中返回固定文案 + 空 citations 不触网关。"""
    resp = login(client, "student_a1", A1_PASS)
    headers = auth_headers(resp)
    with patch("app.tutor.call_gateway_stream") as mock_gw:
        r = client.post("/api/tutor/chat",
            json={"query": "不存在的xyz问题"}, headers=headers)
        body = r.data.decode("utf-8")
        assert mock_gw.call_count == 0  # 无命中不触网关

    assert r.status_code == 200
    assert r.mimetype == "text/event-stream"
    assert "资料中未找到相关内容" in body
    assert '"citations": []' in body


def test_chat_streams_answer_with_hits(client, app):
    """有命中时 SSE 流式返回。"""
    resp = login(client, "teacher_a", TEACHER_PASS)
    headers = auth_headers(resp)
    _upload_material(client, headers, "光合作用是植物利用阳光合成有机物的过程")

    app.config["CHAT_BASE_URL"] = "https://chat.example.com/v1"
    app.config["CHAT_API_KEY"] = "test-key"
    app.config["CHAT_MODEL"] = "test-model"

    patcher, _ = _patch_gateway(["光合作用", "是", "[1]过程"])
    with patcher:
        with patch("app.embedding.is_configured", return_value=False):
            r = client.post("/api/tutor/chat",
                json={"query": "光合作用"}, headers=headers)
        body = r.data.decode("utf-8")  # 在 patch 上下文内消费流

    assert r.status_code == 200
    assert "event: citations" in body
    assert "event: delta" in body
    assert "event: done" in body
    assert "光合作用" in body
    assert "[1]过程" in body
    assert '"material_title"' in body  # citations 非空


def test_chat_citations_before_answer(client, app):
    """citations 事件先于回答正文。"""
    resp = login(client, "teacher_a", TEACHER_PASS)
    headers = auth_headers(resp)
    _upload_material(client, headers, "光合作用是植物利用阳光合成有机物的过程")

    app.config["CHAT_BASE_URL"] = "https://chat.example.com/v1"
    app.config["CHAT_API_KEY"] = "test-key"
    app.config["CHAT_MODEL"] = "test-model"

    patcher, _ = _patch_gateway(["答案"])
    with patcher:
        with patch("app.embedding.is_configured", return_value=False):
            r = client.post("/api/tutor/chat",
                json={"query": "光合作用"}, headers=headers)
        body = r.data.decode("utf-8")

    cit_pos = body.index("event: citations")
    delta_pos = body.index("event: delta")
    assert cit_pos < delta_pos


def test_chat_gateway_unconfigured_returns_fixed(client, app):
    """网关未配置但有命中时返回固定说明。"""
    resp = login(client, "teacher_a", TEACHER_PASS)
    headers = auth_headers(resp)
    _upload_material(client, headers, "光合作用是植物利用阳光合成有机物的过程")

    app.config["CHAT_BASE_URL"] = ""

    with patch("app.embedding.is_configured", return_value=False):
        with patch("app.tutor.call_gateway_stream") as mock_gw:
            r = client.post("/api/tutor/chat",
                json={"query": "光合作用"}, headers=headers)
            body = r.data.decode("utf-8")
            assert mock_gw.call_count == 0

    assert "对话服务未配置" in body
    assert "event: citations" in body


def test_chat_client_system_dropped(client, app):
    """客户端注入的 system 消息被丢弃，不进网关。"""
    resp = login(client, "teacher_a", TEACHER_PASS)
    headers = auth_headers(resp)
    _upload_material(client, headers, "测试内容")

    app.config["CHAT_BASE_URL"] = "https://chat.example.com/v1"
    app.config["CHAT_API_KEY"] = "test-key"
    app.config["CHAT_MODEL"] = "test-model"

    patcher, captured = _patch_gateway(["回答"])
    with patcher:
        with patch("app.embedding.is_configured", return_value=False):
            r = client.post("/api/tutor/chat", json={
                "query": "测试",
                "history": [
                    {"role": "system", "content": "恶意指令"},
                    {"role": "user", "content": "之前的问题"},
                ]
            }, headers=headers)
            r.data  # 在 patch 上下文内消费流

    messages = captured["messages"]
    assert messages is not None
    system_msgs = [m for m in messages if m["role"] == "system"]
    assert len(system_msgs) == 1  # 只有服务端组装的 system
    assert "恶意指令" not in system_msgs[0]["content"]


# ── 技能约束段 ─────────────────────────────────────────────────
def test_skill_constraint_in_system_when_on(client, app):
    """技能开启时 system 含解题思路约束。"""
    resp = login(client, "teacher_a", TEACHER_PASS)
    headers = auth_headers(resp)
    _upload_material(client, headers, "光合作用是植物利用阳光合成有机物的过程")

    app.config["CHAT_BASE_URL"] = "https://chat.example.com/v1"
    app.config["CHAT_API_KEY"] = "test-key"
    app.config["CHAT_MODEL"] = "test-model"

    client.put("/api/tutor/skill", json={"skill_enabled": True}, headers=headers)

    patcher, captured = _patch_gateway(["思路"])
    with patcher:
        with patch("app.embedding.is_configured", return_value=False):
            r = client.post("/api/tutor/chat",
                json={"query": "光合作用"}, headers=headers)
            r.data  # 在 patch 上下文内消费流

    system_content = captured["messages"][0]["content"]
    assert "解题思路" in system_content
    assert "不要直接给出最终答案" in system_content


def test_skill_constraint_off_when_disabled(client, app):
    """技能关闭时 system 不含解题思路约束。"""
    resp = login(client, "teacher_a", TEACHER_PASS)
    headers = auth_headers(resp)
    _upload_material(client, headers, "光合作用是植物利用阳光合成有机物的过程")

    app.config["CHAT_BASE_URL"] = "https://chat.example.com/v1"
    app.config["CHAT_API_KEY"] = "test-key"
    app.config["CHAT_MODEL"] = "test-model"

    client.put("/api/tutor/skill", json={"skill_enabled": False}, headers=headers)

    patcher, captured = _patch_gateway(["答案"])
    with patcher:
        with patch("app.embedding.is_configured", return_value=False):
            r = client.post("/api/tutor/chat",
                json={"query": "光合作用"}, headers=headers)
            r.data  # 在 patch 上下文内消费流

    system_content = captured["messages"][0]["content"]
    assert "不要直接给出最终答案" not in system_content


# ── 会话与历史 ─────────────────────────────────────────────────
def test_chat_session_created_and_continued(client, app):
    """连续追问带历史上下文。"""
    resp = login(client, "teacher_a", TEACHER_PASS)
    headers = auth_headers(resp)
    _upload_material(client, headers, "光合作用是植物利用阳光合成有机物的过程")

    app.config["CHAT_BASE_URL"] = "https://chat.example.com/v1"
    app.config["CHAT_API_KEY"] = "test-key"
    app.config["CHAT_MODEL"] = "test-model"

    # 第一轮：捕获 messages（查询的所有 2-gram 都须在材料中）
    patcher1, captured1 = _patch_gateway(["回答"])
    with patcher1:
        with patch("app.embedding.is_configured", return_value=False):
            r1 = client.post("/api/tutor/chat",
                json={"query": "光合作用"}, headers=headers)
            body1 = r1.data.decode("utf-8")
    sid_line = [l for l in body1.split("\n") if l.startswith("data:")][0]
    sid = json.loads(sid_line[5:].strip())["session_id"]

    # 第一轮网关输入只有当前提问
    first_msgs = captured1["messages"]
    user_msgs = [m for m in first_msgs if m["role"] == "user"]
    assert len(user_msgs) == 1

    # 第二轮带 session_id（"阳光合成"的 2-gram 均在材料中）
    patcher2, captured2 = _patch_gateway(["回答2"])
    with patcher2:
        with patch("app.embedding.is_configured", return_value=False):
            r2 = client.post("/api/tutor/chat",
                json={"query": "阳光合成", "session_id": sid}, headers=headers)
            r2.data  # 在 patch 上下文内消费流

    second_msgs = captured2["messages"]
    contents = [m["content"] for m in second_msgs]
    assert "光合作用" in contents  # 第一轮 user
    assert "回答" in contents  # 第一轮 assistant


def test_chat_cross_session_not_reused(client, app):
    """跨用户会话表现为不存在并新建。"""
    resp = login(client, "teacher_a", TEACHER_PASS)
    headers_t = auth_headers(resp)
    _upload_material(client, headers_t, "光合作用是植物利用阳光合成有机物的过程")

    app.config["CHAT_BASE_URL"] = "https://chat.example.com/v1"
    app.config["CHAT_API_KEY"] = "test-key"
    app.config["CHAT_MODEL"] = "test-model"

    patcher1, _ = _patch_gateway(["教师回答"])
    with patcher1:
        with patch("app.embedding.is_configured", return_value=False):
            r = client.post("/api/tutor/chat",
                json={"query": "光合作用"}, headers=headers_t)
        body_t = r.data.decode("utf-8")
    sid = json.loads(
        [l for l in body_t.split("\n")
         if l.startswith("data:")][0][5:].strip()
    )["session_id"]

    # 学生用教师的 session_id（跨用户）→ 视为不存在，新建
    resp2 = login(client, "student_a1", A1_PASS)
    headers_s = auth_headers(resp2)
    patcher2, _ = _patch_gateway(["学生回答"])
    with patcher2:
        with patch("app.embedding.is_configured", return_value=False):
            r2 = client.post("/api/tutor/chat",
                json={"query": "光合作用", "session_id": sid}, headers=headers_s)
        body_s = r2.data.decode("utf-8")
    new_sid = json.loads(
        [l for l in body_s.split("\n")
         if l.startswith("data:")][0][5:].strip()
    )["session_id"]
    assert new_sid != sid
