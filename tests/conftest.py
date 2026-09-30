"""pytest 公共夹具：临时数据库 + 临时上传目录 + 已灌种子的应用。"""

import pytest

from app import create_app
from app.db import init_db
from app.seed import seed_data

# 与 .env.example 演示值不同的测试口令
TEACHER_PASS = "teacher-a-pass-123"
A1_PASS = "student-a1-pass-123"
B1_PASS = "student-b1-pass-123"


@pytest.fixture
def app(tmp_path):
    application = create_app(
        {
            "SECRET_KEY": "test-secret-key",
            "DATABASE_PATH": str(tmp_path / "test.db"),
            "UPLOAD_DIR": str(tmp_path / "uploads"),
            # 小上限，便于 413 用例
            "MAX_CONTENT_LENGTH": 1024,
            "SEED_TEACHER_A_PASSWORD": TEACHER_PASS,
            "SEED_STUDENT_A1_PASSWORD": A1_PASS,
            "SEED_STUDENT_B1_PASSWORD": B1_PASS,
            "JWT_EXPIRES": 3600,
            "TESTING": True,
        }
    )
    with application.app_context():
        init_db()
        seed_data()
    return application


@pytest.fixture
def client(app):
    return app.test_client()


def login(client, username: str, password: str):
    return client.post(
        "/api/login", json={"username": username, "password": password}
    )


def auth_headers(resp) -> dict:
    """从登录响应中提取 token，返回 Authorization 头。"""
    token = resp.get_json().get("token", "")
    return {"Authorization": f"Bearer {token}"}
