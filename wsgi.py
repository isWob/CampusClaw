"""gunicorn 入口：wsgi:app。

gunicorn 加载本模块时即从环境读取配置；必需变量缺失则导入失败、进程退出，
满足「密钥缺失拒绝启动」。
"""

from dotenv import load_dotenv

load_dotenv()

from app import create_app  # noqa: E402

app = create_app()
