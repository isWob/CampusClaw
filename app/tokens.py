"""JWT 吊销清单仓储（replace-session-with-jwt）。"""

import time

from .db import get_db


def revoke(jti: str, exp: int) -> None:
    """将 jti 写入吊销清单。"""
    db = get_db()
    db.execute(
        "INSERT OR REPLACE INTO revoked_tokens (jti, exp) VALUES (?, ?)",
        (jti, exp),
    )
    db.commit()


def is_revoked(jti: str) -> bool:
    """检查 jti 是否在吊销清单中。"""
    db = get_db()
    row = db.execute(
        "SELECT 1 FROM revoked_tokens WHERE jti = ?", (jti,)
    ).fetchone()
    return row is not None


def cleanup_expired() -> None:
    """清理已过期的吊销条目。"""
    db = get_db()
    now = int(time.time())
    db.execute("DELETE FROM revoked_tokens WHERE exp < ?", (now,))
    db.commit()
