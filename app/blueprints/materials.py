"""材料知识库（specs/class-materials）。

- GET  /api/materials               本班材料列表（班级条件只取自会话）；
- POST /api/materials               仅教师可上传，学生 403；
- GET  /api/materials/<id>          详情：先取行再核对班级，跨班同形 404；
- GET  /api/materials/<id>/download 鉴权下载，不静态暴露上传目录。
"""

from pathlib import Path

from flask import (
    Blueprint, current_app, g, jsonify, request, send_from_directory,
)

from .. import repositories as repos
from ..db import get_db
from ..services import UploadError, save_material_upload

bp = Blueprint("materials", __name__)


def _material_dict(row) -> dict:
    """对外元数据：不含 stored_path 等服务端磁盘绝对路径。"""
    return {
        "id": row["id"],
        "class_id": row["class_id"],
        "class_name": row["class_name"],
        "filename": row["filename"],
        "uploader_id": row["uploader_id"],
        "uploader_name": row["uploader_name"],
        "created_at": row["created_at"],
    }


def _fetch_owned_or_404(material_id: int):
    """对象路径 fetch-then-check：跨班与不存在返回完全同形的 404。"""
    row = repos.get_material_by_id(get_db(), material_id)
    if row is None or row["class_id"] != g.current_user["class_id"]:
        if row is not None:
            # 真实原因只进服务端日志，对外与"不存在"不可区分
            current_app.logger.warning(
                "跨班材料访问被拒绝 user_id=%s user_class=%s material_class=%s material_id=%s",
                g.current_user["id"], g.current_user["class_id"],
                row["class_id"], material_id,
            )
        return None, (jsonify({"error": "材料不存在"}), 404)
    return row, None


@bp.get("/api/materials")
def list_materials():
    rows = repos.list_materials(get_db(), g.current_user["class_id"])
    return jsonify([_material_dict(r) for r in rows]), 200


@bp.post("/api/materials")
def upload_material():
    # 角色闸门在服务端（BFLA）：学生 403，且不触达任何存储
    if g.current_user["role"] != "teacher":
        return jsonify({"error": "仅教师可上传材料"}), 403

    file_storage = request.files.get("file")
    if file_storage is None or not file_storage.filename:
        return jsonify({"error": "未提供上传文件"}), 400

    try:
        material_id = save_material_upload(
            get_db(),
            Path(current_app.config["UPLOAD_DIR"]),
            g.current_user,
            file_storage,
        )
    except UploadError as exc:
        return jsonify({"error": exc.message}), exc.status

    return jsonify({"id": material_id}), 201


@bp.get("/api/materials/<int:material_id>")
def material_detail(material_id: int):
    row, error = _fetch_owned_or_404(material_id)
    if error is not None:
        return error
    return jsonify(_material_dict(row)), 200


@bp.get("/api/materials/<int:material_id>/download")
def material_download(material_id: int):
    row, error = _fetch_owned_or_404(material_id)
    if error is not None:
        return error
    # 目录固定为 UPLOAD_DIR，文件名为服务端生成的存储名，客户端无法构造路径
    return send_from_directory(
        Path(current_app.config["UPLOAD_DIR"]),
        row["stored_path"],
        as_attachment=True,
        download_name=row["filename"],
    )
