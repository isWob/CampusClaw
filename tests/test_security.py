"""密码哈希（tasks 4.1 / 4.2）。"""

from app.security import check_password, hash_password


def test_hash_roundtrip():
    h = hash_password("s3cret-pw")
    assert h != "s3cret-pw"
    assert check_password("s3cret-pw", h) is True


def test_hash_is_salted_and_not_plaintext():
    h1 = hash_password("same-pw")
    h2 = hash_password("same-pw")
    assert h1 != h2  # 自带盐：同一明文两次哈希不同
    assert "same-pw" not in h1 and "same-pw" not in h2


def test_wrong_password_fails():
    assert check_password("wrong", hash_password("right")) is False


def test_check_against_missing_hash_is_false():
    # 用户不存在路径：执行哑哈希比较但不抛错、不通过
    assert check_password("any-pw", None) is False
