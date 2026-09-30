"""JWT 签发与验证（replace-session-with-jwt）。

HS256 + SECRET_KEY；载荷含 sub/role/class_id/iat/exp/jti。
sub 按 RFC 7519 要求为字符串（user id 的字符串形式），验签后由调用方转回 int。
"""

import time
import uuid

import jwt


def sign_token(user: dict, secret: str, expires: int) -> str:
    """签发 JWT。载荷不含密码等敏感信息；sub 为用户 id 的字符串形式。"""
    now = int(time.time())
    payload = {
        "sub": str(user["id"]),
        "role": user["role"],
        "class_id": user["class_id"],
        "iat": now,
        "exp": now + expires,
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def verify_token(token: str, secret: str) -> dict | None:
    """验签 + 验过期；返回 payload 或 None。"""
    try:
        return jwt.decode(token, secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
