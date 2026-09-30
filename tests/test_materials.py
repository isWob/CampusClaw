"""上传授权、校验链、班级隔离（tasks 7.1–7.5、8.1–8.2，specs/class-materials）。"""

from io import BytesIO
from pathlib import Path

import pytest

from app import repositories as repos
from app.db import get_db

from .conftest import A1_PASS, B1_PASS, TEACHER_PASS, auth_headers, login


class _AuthedClient:
    """包装 Flask test_client，自动注入 Authorization: Bearer 头。

    用于以 JWT（而非依赖 test_client 的 Cookie jar）发起受保护请求。
    """

    def __init__(self, client, token: str):
        self._client = client
        self._headers = {"Authorization": f"Bearer {token}"}

    def get(self, *args, **kwargs):
        headers = dict(self._headers)
        headers.update(kwargs.pop("headers", None) or {})
        return self._client.get(*args, headers=headers, **kwargs)

    def post(self, *args, **kwargs):
        headers = dict(self._headers)
        headers.update(kwargs.pop("headers", None) or {})
        return self._client.post(*args, headers=headers, **kwargs)


@pytest.fixture
def personas(app):
    teacher = app.test_client()
    student_a = app.test_client()
    student_b = app.test_client()

    teacher_resp = login(teacher, "teacher_a", TEACHER_PASS)
    student_a_resp = login(student_a, "student_a1", A1_PASS)
    student_b_resp = login(student_b, "student_b1", B1_PASS)
    assert teacher_resp.status_code == 200
    assert student_a_resp.status_code == 200
    assert student_b_resp.status_code == 200

    teacher = _AuthedClient(teacher, teacher_resp.get_json()["token"])
    student_a = _AuthedClient(student_a, student_a_resp.get_json()["token"])
    student_b = _AuthedClient(student_b, student_b_resp.get_json()["token"])
    return app, teacher, student_a, student_b


def upload(client, filename: str, content: bytes, extra_fields=None):
    data = {"file": (BytesIO(content), filename)}
    if extra_fields:
        data.update(extra_fields)
    return client.post(
        "/api/materials", data=data, content_type="multipart/form-data"
    )


def material_count(app) -> int:
    with app.app_context():
        return repos.count_materials(get_db())


def disk_files(app) -> set[str]:
    return {p.name for p in Path(app.config["UPLOAD_DIR"]).iterdir()}


# ── 主路径：教师上传入库 ──────────────────────────────────────────────

def test_teacher_upload_persists_record_and_file(personas):
    app, teacher, _, _ = personas
    before = material_count(app)
    files_before = disk_files(app)

    resp = upload(teacher, "第三单元教案.txt", "教研材料正文".encode("utf-8"))

    assert resp.status_code == 201
    new_id = resp.get_json()["id"]
    assert material_count(app) == before + 1
    assert disk_files(app) - files_before  # 磁盘新增一个文件

    with app.app_context():
        row = repos.get_material_by_id(get_db(), new_id)
        assert row is not None
        assert row["class_id"] == teacher.get("/api/me").get_json()["class_id"]
        assert row["uploader_name"] == "teacher_a"
        assert Path(app.config["UPLOAD_DIR"], row["stored_path"]).exists()


def test_new_upload_visible_in_class_list(personas):
    app, teacher, student_a, _ = personas
    new_id = upload(teacher, "可见性.md", b"# hello").get_json()["id"]

    teacher_ids = {m["id"] for m in teacher.get("/api/materials").get_json()}
    student_ids = {m["id"] for m in student_a.get("/api/materials").get_json()}
    assert new_id in teacher_ids and new_id in student_ids


# ── 垂直越权：学生 403 且不触达存储 ───────────────────────────────────

def test_student_upload_403_without_touching_storage(personas):
    app, _, student_a, _ = personas
    before = material_count(app)
    files_before = disk_files(app)

    resp = upload(student_a, "student-try.txt", b"data")

    assert resp.status_code == 403
    assert material_count(app) == before
    assert disk_files(app) == files_before


# ── 水平越权：跨班同形 404 ────────────────────────────────────────────

def test_cross_class_detail_is_indistinguishable_404(personas):
    _, teacher, _, student_b = personas

    b_listing = student_b.get("/api/materials").get_json()
    b_material_id = b_listing[0]["id"]

    cross = teacher.get(f"/api/materials/{b_material_id}")
    missing = teacher.get("/api/materials/999999")
    assert cross.status_code == 404 and missing.status_code == 404
    assert cross.get_json() == missing.get_json() == {"error": "材料不存在"}
    assert "B班" not in cross.get_data(as_text=True)


def test_cross_class_download_404(personas):
    _, _, student_a, student_b = personas
    b_material_id = student_b.get("/api/materials").get_json()[0]["id"]
    resp = student_a.get(f"/api/materials/{b_material_id}/download")
    assert resp.status_code == 404
    assert "B 班" not in resp.get_data(as_text=True)


def test_class_id_query_param_ignored(personas):
    _, teacher, _, student_b = personas
    b_id = student_b.get("/api/materials").get_json()[0]["id"]
    # 试图用 query/参数声明他班身份，结果不变
    resp = teacher.get(f"/api/materials/{b_id}?class_id={999}")
    assert resp.status_code == 404
    listing = teacher.get("/api/materials?class_id=999").get_json()
    assert all(m["class_name"] == "A班" for m in listing)


def test_uploaded_class_comes_from_session_not_form(personas):
    app, teacher, _, _ = personas
    resp = upload(
        teacher, "injected.txt", b"x",
        extra_fields={"class_id": "999"},
    )
    assert resp.status_code == 201
    with app.app_context():
        row = repos.get_material_by_id(get_db(), resp.get_json()["id"])
        assert row["class_id"] == teacher.get("/api/me").get_json()["class_id"]


# ── 校验链：失败无残留 ────────────────────────────────────────────────

def test_bad_extension_rejected_without_residue(personas):
    app, teacher, _, _ = personas
    for bad_name in ("tool.exe", "note.md.exe", "noext"):
        before = material_count(app)
        files_before = disk_files(app)
        resp = upload(teacher, bad_name, b"abc")
        assert resp.status_code == 400, bad_name
        assert material_count(app) == before
        assert disk_files(app) == files_before


def test_oversized_upload_413_without_residue(personas):
    app, teacher, _, _ = personas
    before = material_count(app)
    files_before = disk_files(app)
    resp = upload(teacher, "big.txt", b"x" * 2048)  # 夹具上限 1024
    assert resp.status_code == 413
    assert material_count(app) == before
    assert disk_files(app) == files_before


def test_empty_and_non_utf8_rejected_without_residue(personas):
    app, teacher, _, _ = personas
    for name, content in (("empty.txt", b""), ("binary.txt", b"\xff\xfe\xfa")):
        before = material_count(app)
        files_before = disk_files(app)
        resp = upload(teacher, name, content)
        assert resp.status_code == 400, name
        assert material_count(app) == before
        assert disk_files(app) == files_before


def test_path_traversal_filename_cannot_escape_upload_dir(personas):
    app, teacher, _, _ = personas
    resp = upload(teacher, "../../evil.txt", b"x")
    assert resp.status_code == 201
    upload_dir = Path(app.config["UPLOAD_DIR"])
    assert not (upload_dir.parent / "evil.txt").exists()
    assert not (upload_dir.parent.parent / "evil.txt").exists()
    with app.app_context():
        row = repos.get_material_by_id(get_db(), resp.get_json()["id"])
        # 存储名由服务端生成，不含客户端路径片段
        assert ".." not in row["stored_path"] and "/" not in row["stored_path"]


# ── 详情与下载走鉴权接口 ──────────────────────────────────────────────

def test_detail_hides_disk_path_and_download_works(personas):
    _, teacher, student_a, _ = personas
    new_id = upload(teacher, "syllabus.md", b"# body").get_json()["id"]

    detail = teacher.get(f"/api/materials/{new_id}")
    assert detail.status_code == 200
    payload = detail.get_json()
    assert "stored_path" not in payload
    assert payload["filename"].endswith("syllabus.md")

    # 本班学生可下载，内容一致
    download = student_a.get(f"/api/materials/{new_id}/download")
    assert download.status_code == 200
    assert download.data == b"# body"


def test_upload_dir_is_not_static_served(personas):
    _, teacher, _, _ = personas
    resp = teacher.get("/uploads/seed-class-a.txt")
    assert resp.status_code != 200
    assert "A 班的预置教研材料" not in resp.get_data(as_text=True)


# ── 服务端渲染页面也服从班级边界 ──────────────────────────────────────

def test_materials_page_lists_only_own_class(personas):
    _, teacher, _, student_b = personas
    page_a = teacher.get("/materials").get_data(as_text=True)
    page_b = student_b.get("/materials").get_data(as_text=True)
    assert "A班-语文教研大纲" in page_a
    assert "B班-数学教研大纲" not in page_a
    assert "B班-数学教研大纲" in page_b
    # 学生页面不渲染上传入口
    assert "上传入库" not in page_b


def test_page_form_upload_teacher_only(personas):
    _, _, student_a, _ = personas
    resp = student_a.post(
        "/materials/upload",
        data={"file": (BytesIO(b"x"), "x.txt")},
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    assert resp.status_code == 403
