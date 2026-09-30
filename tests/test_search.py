"""检索测试。"""

import pytest
from app.db import get_db, init_db
from app.indexing import build_index
from app.search import keyword_search, hybrid_search, search
from .conftest import TEACHER_PASS, login, auth_headers


def _upload_and_index(app, client, filename, content):
    """上传材料并确保索引建立。"""
    from io import BytesIO
    resp = client.post("/api/materials",
        data={"file": (BytesIO(content), filename)},
        content_type="multipart/form-data")
    assert resp.status_code == 201
    return resp.get_json()["id"]


def test_keyword_search_finds_content(client, app):
    resp = login(client, "teacher_a", TEACHER_PASS)
    headers = auth_headers(resp)

    _upload_and_index(app, client, "lesson.txt", "光合作用是植物利用阳光合成有机物的过程".encode("utf-8"))

    with app.app_context():
        db = get_db()
        hits = keyword_search("光合作用", 1, db)
        assert len(hits) > 0
        assert any("光合" in h["excerpt"] for h in hits)


def test_keyword_search_no_hit(client, app):
    resp = login(client, "teacher_a", TEACHER_PASS)
    headers = auth_headers(resp)

    with app.app_context():
        db = get_db()
        hits = keyword_search("不存在的词xyz", 1, db)
        assert hits == []


def test_empty_query_returns_400(client):
    resp = login(client, "teacher_a", TEACHER_PASS)
    headers = auth_headers(resp)

    resp = client.post("/api/search",
        json={"query": "", "mode": "keyword"}, headers=headers)
    assert resp.status_code == 400


def test_search_no_hit_message(client, app):
    resp = login(client, "teacher_a", TEACHER_PASS)
    headers = auth_headers(resp)

    resp = client.post("/api/search",
        json={"query": "不存在的xyz", "mode": "keyword"}, headers=headers)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["hits"] == []
    assert "未找到" in data["message"]


def test_cross_class_search_no_hit(client, app):
    """跨班检索对外表现为无命中。"""
    resp = login(client, "teacher_a", TEACHER_PASS)
    headers = auth_headers(resp)

    # 上传 A 班材料
    _upload_and_index(app, client, "a-lesson.txt", "A班专属内容光合作用".encode("utf-8"))

    # 用 B 班学生搜索 A 班内容
    from .conftest import B1_PASS
    resp2 = login(client, "student_b1", B1_PASS)
    headers2 = auth_headers(resp2)

    resp3 = client.post("/api/search",
        json={"query": "光合作用", "mode": "keyword"}, headers=headers2)
    assert resp3.status_code == 200
    assert resp3.get_json()["hits"] == []


def test_vector_search_503_without_config(client):
    """向量检索在未配置嵌入时返回 503。"""
    resp = login(client, "teacher_a", TEACHER_PASS)
    headers = auth_headers(resp)

    resp = client.post("/api/search",
        json={"query": "test", "mode": "vector"}, headers=headers)
    assert resp.status_code == 503
