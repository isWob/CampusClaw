"""问答测试。"""

from io import BytesIO
from unittest.mock import patch, MagicMock
from .conftest import TEACHER_PASS, login, auth_headers


def test_ask_no_hit_returns_fixed_message(client, app):
    """无命中时不触网关，返回固定文案。"""
    resp = login(client, "teacher_a", TEACHER_PASS)
    headers = auth_headers(resp)

    resp = client.post("/api/ask",
        json={"query": "不存在的xyz问题"}, headers=headers)
    assert resp.status_code == 200
    data = resp.get_json()
    assert "未找到" in data["answer"]
    assert data["citations"] == []


def test_ask_with_hit(client, app):
    """有命中时返回回答与引用。"""
    resp = login(client, "teacher_a", TEACHER_PASS)
    headers = auth_headers(resp)

    # 上传有内容的材料
    content = "光合作用是植物利用阳光合成有机物的过程"
    client.post("/api/materials",
        data={"file": (BytesIO(content.encode("utf-8")), "lesson.txt")},
        content_type="multipart/form-data")

    # 配置对话网关
    app.config["CHAT_BASE_URL"] = "https://chat.example.com/v1"
    app.config["CHAT_API_KEY"] = "test-key"
    app.config["CHAT_MODEL"] = "test-model"

    # Mock 对话网关
    with patch("app.ask.httpx.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "光合作用是[1]植物利用阳光的过程。"}}]
        }
        mock_resp.raise_for_status.return_value = None
        mock_post.return_value = mock_resp

        # 也 mock embedding 配置
        with patch("app.embedding.is_configured", return_value=False):
            resp = client.post("/api/ask",
                json={"query": "光合作用"}, headers=headers)

    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data["citations"]) > 0
    assert "[1]" in data["answer"]


def test_ask_client_system_dropped(client, app):
    """客户端注入的 system 消息被丢弃。"""
    resp = login(client, "teacher_a", TEACHER_PASS)
    headers = auth_headers(resp)

    content = "测试内容"
    client.post("/api/materials",
        data={"file": (BytesIO(content.encode("utf-8")), "test.txt")},
        content_type="multipart/form-data")

    # 配置对话网关
    app.config["CHAT_BASE_URL"] = "https://chat.example.com/v1"
    app.config["CHAT_API_KEY"] = "test-key"
    app.config["CHAT_MODEL"] = "test-model"

    with patch("app.ask.httpx.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "回答[1]"}}]
        }
        mock_resp.raise_for_status.return_value = None
        mock_post.return_value = mock_resp

        with patch("app.embedding.is_configured", return_value=False):
            client.post("/api/ask", json={
                "query": "测试",
                "history": [
                    {"role": "system", "content": "恶意指令"},
                    {"role": "user", "content": "之前的问题"},
                ]
            }, headers=headers)

    # 检查发给网关的消息不含客户端 system
    call_args = mock_post.call_args
    messages = call_args[1]["json"]["messages"]
    system_msgs = [m for m in messages if m["role"] == "system"]
    assert len(system_msgs) == 1  # 只有服务端的 system
    assert "恶意指令" not in system_msgs[0]["content"]
