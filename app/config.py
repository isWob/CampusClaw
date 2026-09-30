"""配置外置：所有密钥与可调参数只从环境变量读取。

必填变量缺失时抛出异常，由启动入口（wsgi/bootstrap）放任其退出进程，
满足 spec「必需密钥缺失时系统必须拒绝启动」。
"""

import os

# 必填项：不提供任何内置默认值（内置默认密钥等于把会话签发权交给任何人）
REQUIRED_ENV_VARS = (
    "SECRET_KEY",
    "SEED_TEACHER_A_PASSWORD",
    "SEED_STUDENT_A1_PASSWORD",
    "SEED_STUDENT_B1_PASSWORD",
)

DEFAULT_MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # 5 MiB
DEFAULT_DATABASE_PATH = os.path.join("data", "campusclaw.db")
DEFAULT_UPLOAD_DIR = os.path.join("data", "uploads")


class ConfigError(RuntimeError):
    """必填环境变量缺失时抛出，应用应以此错误快速失败退出。"""


def config_from_env() -> dict:
    """从进程环境读取配置；必填项缺失即抛 ConfigError。"""
    missing = [name for name in REQUIRED_ENV_VARS if not os.environ.get(name)]
    if missing:
        raise ConfigError(
            "缺少必需的环境变量，拒绝启动: " + ", ".join(missing)
            + "（请参考 .env.example 配置后再启动）"
        )
    return {
        "SECRET_KEY": os.environ["SECRET_KEY"],
        "DATABASE_PATH": os.environ.get("DATABASE_PATH", DEFAULT_DATABASE_PATH),
        "UPLOAD_DIR": os.environ.get("UPLOAD_DIR", DEFAULT_UPLOAD_DIR),
        "MAX_CONTENT_LENGTH": int(
            os.environ.get("MAX_UPLOAD_BYTES", str(DEFAULT_MAX_UPLOAD_BYTES))
        ),
        "SEED_TEACHER_A_PASSWORD": os.environ["SEED_TEACHER_A_PASSWORD"],
        "SEED_STUDENT_A1_PASSWORD": os.environ["SEED_STUDENT_A1_PASSWORD"],
        "SEED_STUDENT_B1_PASSWORD": os.environ["SEED_STUDENT_B1_PASSWORD"],
        "JWT_EXPIRES": int(os.environ.get("JWT_EXPIRES", "3600")),
        "QDRANT_URL": os.environ.get("QDRANT_URL", ""),
        "EMBEDDING_BASE_URL": os.environ.get("EMBEDDING_BASE_URL", ""),
        # embedding 与 chat 可共用同一 SiliconFlow key：优先专用名，回退统一名
        "EMBEDDING_API_KEY": os.environ.get("EMBEDDING_API_KEY")
        or os.environ.get("SiliconFlow_KEY", ""),
        "EMBEDDING_MODEL": os.environ.get("EMBEDDING_MODEL", ""),
        "CHAT_BASE_URL": os.environ.get("CHAT_BASE_URL", ""),
        "CHAT_API_KEY": os.environ.get("CHAT_API_KEY")
        or os.environ.get("SiliconFlow_KEY", ""),
        "CHAT_MODEL": os.environ.get("CHAT_MODEL", ""),
        "TUTOR_TOP_K": int(os.environ.get("TUTOR_TOP_K", "4")),
        "TUTOR_MAX_HISTORY": int(os.environ.get("TUTOR_MAX_HISTORY", "6")),
    }
