"""数据访问层（design Decision 4）。

材料读取只有这一个模块对外提供，任何材料查询都必须在这里带上班级边界：
- 列表路径：SQL 直接带 WHERE class_id = 会话班级；
- 对象路径：按 id 先取行（fetch），归属核对（check）交给服务层，
  使「跨班」与「id 不存在」能返回同形 404。
"""

import sqlite3


def get_user_by_username(db: sqlite3.Connection, username: str) -> sqlite3.Row | None:
    return db.execute(
        "SELECT id, username, password_hash, role, class_id FROM users WHERE username = ?",
        (username,),
    ).fetchone()


def get_user_by_id(db: sqlite3.Connection, user_id: int) -> sqlite3.Row | None:
    return db.execute(
        "SELECT id, username, password_hash, role, class_id FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()


def list_materials(db: sqlite3.Connection, class_id: int) -> list[sqlite3.Row]:
    """集合路径：班级条件只来自服务端会话，客户端传入的 class_id 到不了这里。"""
    return db.execute(
        """
        SELECT m.id, m.class_id, m.uploader_id, m.filename, m.stored_path,
               m.created_at, u.username AS uploader_name, c.name AS class_name
        FROM materials m
        JOIN users u ON u.id = m.uploader_id
        JOIN classes c ON c.id = m.class_id
        WHERE m.class_id = ?
        ORDER BY m.created_at DESC, m.id DESC
        """,
        (class_id,),
    ).fetchall()


def get_material_by_id(db: sqlite3.Connection, material_id: int) -> sqlite3.Row | None:
    """对象路径第一步：按 id 取行，不在 SQL 中预过滤班级。"""
    return db.execute(
        """
        SELECT m.id, m.class_id, m.uploader_id, m.filename, m.stored_path,
               m.created_at, u.username AS uploader_name, c.name AS class_name
        FROM materials m
        JOIN users u ON u.id = m.uploader_id
        JOIN classes c ON c.id = m.class_id
        WHERE m.id = ?
        """,
        (material_id,),
    ).fetchone()


def insert_material(
    db: sqlite3.Connection,
    *,
    class_id: int,
    uploader_id: int,
    filename: str,
    stored_path: str,
    body_text: str = "",
) -> int:
    cur = db.execute(
        "INSERT INTO materials (class_id, uploader_id, filename, stored_path, body_text)"
        " VALUES (?, ?, ?, ?, ?)",
        (class_id, uploader_id, filename, stored_path, body_text),
    )
    db.commit()
    return int(cur.lastrowid)


def count_users(db: sqlite3.Connection) -> int:
    return int(db.execute("SELECT COUNT(*) FROM users").fetchone()[0])


def count_classes(db: sqlite3.Connection) -> int:
    return int(db.execute("SELECT COUNT(*) FROM classes").fetchone()[0])


def count_materials(db: sqlite3.Connection) -> int:
    return int(db.execute("SELECT COUNT(*) FROM materials").fetchone()[0])
