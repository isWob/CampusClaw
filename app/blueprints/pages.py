"""服务端渲染页面（design Decision 9）：登录页与受保护材料页。

不做单独 SPA；身份与班级来自服务端会话，页面只按角色渲染入口，
访问控制完全由 /api 与会话闸门在服务端强制执行。
"""

from pathlib import Path

from flask import (
    Blueprint, current_app, flash, g, redirect, render_template, request,
    url_for,
)

from .. import repositories as repos
from ..db import get_db
from ..services import UploadError, save_material_upload

bp = Blueprint("pages", __name__)


@bp.get("/")
def index():
    return redirect(url_for("pages.materials_page"))


@bp.get("/login")
def login_page():
    # 已登录访问登录页直接进入材料页
    return redirect(url_for("pages.materials_page")) if g.get("current_user") \
        else render_template("login.html", error=None)


@bp.get("/materials")
def materials_page():
    rows = repos.list_materials(get_db(), g.current_user["class_id"])
    return render_template(
        "materials.html",
        user=g.current_user,
        materials=rows,
    )


@bp.post("/materials/upload")
def materials_upload_page():
    """材料页表单上传（PRG）；与 JSON 接口共用同一条服务端校验链。"""
    if g.current_user["role"] != "teacher":
        flash("仅教师可上传材料", "error")
        return redirect(url_for("pages.materials_page")), 403

    file_storage = request.files.get("file")
    if file_storage is None or not file_storage.filename:
        flash("未选择文件", "error")
        return redirect(url_for("pages.materials_page"))

    try:
        save_material_upload(
            get_db(),
            Path(current_app.config["UPLOAD_DIR"]),
            g.current_user,
            file_storage,
        )
    except UploadError as exc:
        flash(exc.message, "error")
    else:
        flash("材料已上传并入库", "ok")
    return redirect(url_for("pages.materials_page"), code=303)
