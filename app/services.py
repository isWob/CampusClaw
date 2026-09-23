"""材料上传业务（design Decision 10）。

顺序：会话/角色在路由层先判；这里负责 校验 → 落盘 → 入库。
任何一步失败都回到「无文件、无记录」：
- 校验不过：不触盘；
- 落盘后写库失败：删除已落盘文件，不留孤儿。
"""

import uuid
from pathlib import Path

from flask import current_app
from werkzeug.utils import secure_filename

ALLOWED_EXTENSIONS = {".txt", ".md"}


class UploadError(Exception):
    def __init__(self, message: str, status: int):
        super().__init__(message)
        self.message = message
        self.status = status


def _extension(filename: str) -> str:
    return Path(filename).suffix.lower()


def save_material_upload(db, upload_dir: Path, user, file_storage) -> int:
    """保存一次教师上传，返回新 material id；失败抛 UploadError（无残留）。"""
    raw_name = file_storage.filename or ""
    safe_name = secure_filename(raw_name)
    ext = _extension(raw_name)

    # 1) 扩展名白名单（不读内容、不触盘）
    if ext not in ALLOWED_EXTENSIONS:
        raise UploadError("仅允许上传 .txt / .md 文件", 400)

    # 2) 读取内容（超限已由 Flask MAX_CONTENT_LENGTH 拦截为 413）
    data = file_storage.read()
    if not data:
        raise UploadError("文件内容不能为空", 400)

    # 3) 非空 UTF-8 文本校验
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        raise UploadError("文件必须是非空 UTF-8 文本", 400)

    # 4) 服务端生成存储名；客户端文件名只作展示，绝不参与路径构造
    stored_name = f"{uuid.uuid4().hex}{ext}"
    destination = upload_dir / stored_name

    try:
        # 5) 先落盘
        destination.write_bytes(data)
        # 6) 再入库；失败则删除已落盘文件
        from . import repositories as repos

        material_id = repos.insert_material(
            db,
            class_id=user["class_id"],       # 租户只取自会话，表单 class_id 被忽略
            uploader_id=user["id"],
            filename=safe_name or stored_name,
            stored_path=stored_name,
        )
    except Exception:
        if destination.exists():
            destination.unlink()
        current_app.logger.exception("材料入库失败，已回滚磁盘文件")
        raise UploadError("材料入库失败", 500)

    return material_id
