"""索引管道测试。"""

from io import BytesIO
from app.db import get_db
from app.indexing import build_index
from app.chunker import _bigram
from .conftest import TEACHER_PASS, login, auth_headers


def test_upload_creates_chunks(client, app):
    resp = login(client, "teacher_a", TEACHER_PASS)
    headers = auth_headers(resp)

    content = "这是教研材料正文内容。包含多个知识点。" * 10
    resp = client.post("/api/materials",
        data={"file": (BytesIO(content.encode("utf-8")), "lesson.txt")},
        content_type="multipart/form-data")
    assert resp.status_code == 201
    material_id = resp.get_json()["id"]

    with app.app_context():
        db = get_db()
        rows = db.execute(
            "SELECT * FROM knowledge_chunks WHERE material_id = ?", (material_id,)
        ).fetchall()
        assert len(rows) > 0
        # FTS 行存在
        fts_rows = db.execute(
            "SELECT chunk_id FROM chunks_fts WHERE chunk_id IN ({})".format(
                ",".join("?" * len(rows))
            ),
            [r["id"] for r in rows]
        ).fetchall()
        assert len(fts_rows) == len(rows)


def test_body_text_saved_on_upload(client, app):
    resp = login(client, "teacher_a", TEACHER_PASS)
    headers = auth_headers(resp)

    content = "正文内容测试"
    resp = client.post("/api/materials",
        data={"file": (BytesIO(content.encode("utf-8")), "test.txt")},
        content_type="multipart/form-data")
    assert resp.status_code == 201

    with app.app_context():
        db = get_db()
        row = db.execute(
            "SELECT body_text FROM materials ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert row["body_text"] == content


def test_reindex_replaces_chunks(client, app):
    resp = login(client, "teacher_a", TEACHER_PASS)
    headers = auth_headers(resp)

    content = "内容内容内容" * 35  # 210 chars, 630 bytes - fits multipart 1024 limit
    resp = client.post("/api/materials",
        data={"file": (BytesIO(content.encode("utf-8")), "reindex.txt")},
        content_type="multipart/form-data")
    material_id = resp.get_json()["id"]

    with app.app_context():
        db = get_db()
        old_count = db.execute(
            "SELECT COUNT(*) FROM knowledge_chunks WHERE material_id = ?", (material_id,)
        ).fetchone()[0]

    # 重建索引
    resp = client.post(f"/api/materials/{material_id}/reindex",
        json={"strategy": "custom", "length": 200, "overlap_pct": 10},
        headers=headers)
    assert resp.status_code == 200

    with app.app_context():
        db = get_db()
        new_count = db.execute(
            "SELECT COUNT(*) FROM knowledge_chunks WHERE material_id = ?", (material_id,)
        ).fetchone()[0]
        assert new_count != old_count  # 策略不同，切片数应变化


def test_reindex_student_403(client):
    from .conftest import A1_PASS
    resp = login(client, "student_a1", A1_PASS)
    headers = auth_headers(resp)

    resp = client.post("/api/materials/1/reindex", json={}, headers=headers)
    assert resp.status_code == 403


def test_bigram_basic():
    result = _bigram("光合作用")
    assert "光合" in result
    "合作用" in result  # adjacent bigram


def test_bigram_single_char():
    assert _bigram("x") == "x"
