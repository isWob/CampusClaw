"""幂等预置（种子）数据（design Decision 8）。

六类核心数据：班级 A、班级 B、教师 teacher_a（A 班）、
学生 student_a1（A 班）、学生 student_b1（B 班）、A/B 两班各一条标题可区分材料。
所有账号口令只以加盐哈希落库，明文仅来自环境变量。
重复执行：存在即跳过，不产生重复记录，也不覆盖后续上传。
"""

from pathlib import Path

from flask import current_app

from .db import get_db
from .security import hash_password

# 班级名 -> (种子存储文件名, 展示标题, 正文)
SEED_MATERIALS = {
    "A班": (
        "seed-class-a.txt",
        "A班-语文教研大纲（种子）.txt",
        "这是 A 班的预置教研材料，仅 A 班成员可见。\n",
    ),
    "B班": (
        "seed-class-b.md",
        "B班-数学教研大纲（种子）.md",
        "# B 班数学教研大纲（种子）\n\n这是 B 班的预置教研材料，仅 B 班成员可见。\n",
    ),
}


def _ensure_class(db, name: str) -> int:
    row = db.execute("SELECT id FROM classes WHERE name = ?", (name,)).fetchone()
    if row is not None:
        return int(row["id"])
    cur = db.execute("INSERT INTO classes (name) VALUES (?)", (name,))
    db.commit()
    return int(cur.lastrowid)


def _ensure_user(db, username: str, password: str, role: str, class_id: int) -> int:
    row = db.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
    if row is not None:
        return int(row["id"])
    cur = db.execute(
        "INSERT INTO users (username, password_hash, role, class_id)"
        " VALUES (?, ?, ?, ?)",
        (username, hash_password(password), role, class_id),
    )
    db.commit()
    return int(cur.lastrowid)


def _ensure_material(
    db, upload_dir: Path, class_id: int, uploader_id: int,
    stored_name: str, display_name: str, content: str,
) -> None:
    row = db.execute(
        "SELECT id FROM materials WHERE class_id = ? AND filename = ?",
        (class_id, display_name),
    ).fetchone()
    if row is not None:
        return
    stored_path = upload_dir / stored_name
    if not stored_path.exists():
        stored_path.write_text(content, encoding="utf-8")
    db.execute(
        "INSERT INTO materials (class_id, uploader_id, filename, stored_path)"
        " VALUES (?, ?, ?, ?)",
        (class_id, uploader_id, display_name, stored_name),
    )
    db.commit()


def seed_data() -> None:
    db = get_db()
    upload_dir = Path(current_app.config["UPLOAD_DIR"])
    upload_dir.mkdir(parents=True, exist_ok=True)

    class_a = _ensure_class(db, "A班")
    class_b = _ensure_class(db, "B班")

    # 三个预置账号（口令来自环境变量，仅以哈希落库）
    teacher_a = _ensure_user(
        db, "teacher_a", current_app.config["SEED_TEACHER_A_PASSWORD"],
        "teacher", class_a,
    )
    _ensure_user(
        db, "student_a1", current_app.config["SEED_STUDENT_A1_PASSWORD"],
        "student", class_a,
    )
    _ensure_user(
        db, "student_b1", current_app.config["SEED_STUDENT_B1_PASSWORD"],
        "student", class_b,
    )

    # 两班各一条标题可区分的种子材料（B 班材料仅以 class_id 归属 B 班；
    # uploader 外键取有效用户 teacher_a，隔离判定只看 class_id）
    for class_id, class_name in ((class_a, "A班"), (class_b, "B班")):
        stored_name, display_name, content = SEED_MATERIALS[class_name]
        _ensure_material(
            db, upload_dir, class_id, teacher_a,
            stored_name, display_name, content,
        )
