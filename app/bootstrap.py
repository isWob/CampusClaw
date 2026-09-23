"""容器/本地启动引导：建表 → 幂等灌种子（在对外提供服务之前完成）。

用法：python -m app.bootstrap
环境变量缺失时 config_from_env 抛错，进程以非零码退出（拒绝启动）。
"""

from dotenv import load_dotenv

from . import create_app
from .db import init_db
from .seed import seed_data


def main() -> None:
    load_dotenv()
    app = create_app()
    with app.app_context():
        init_db()
        seed_data()
    print("数据库初始化与种子数据就绪")


if __name__ == "__main__":
    main()
