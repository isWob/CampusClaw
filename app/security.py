"""密码哈希（design Decision 2）。

仅使用 werkzeug 的加盐哈希（默认 scrypt）；明文不入库、不入日志、不出现在错误信息中。
用户不存在时也做一次哑哈希比较，使两条失败路径耗时与响应同形，防账号枚举。
"""

from werkzeug.security import check_password_hash, generate_password_hash

# 模块加载时生成一次的哑哈希，仅用于用户不存在时消耗与正常校验相当的时间
_DUMMY_HASH = generate_password_hash("dummy-password-for-timing-equalization")


def hash_password(plaintext: str) -> str:
    return generate_password_hash(plaintext)


def check_password(plaintext: str, stored_hash: str | None) -> bool:
    """对提交内容做哈希并与已存哈希比较；绝不读取或比较明文。"""
    if stored_hash is None:
        # 即使没有用户也执行一次哈希比较，避免通过耗时差异枚举账号
        check_password_hash(_DUMMY_HASH, plaintext)
        return False
    return check_password_hash(stored_hash, plaintext)
