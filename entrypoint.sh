#!/bin/sh
# 启动顺序：读环境变量（缺失即拒）→ 建表 → 幂等种子 → 对外服务
set -e

echo "[entrypoint] 初始化数据库与种子数据 ..."
python -m app.bootstrap

echo "[entrypoint] 启动 gunicorn (0.0.0.0:8000) ..."
exec gunicorn --bind 0.0.0.0:8000 --workers 2 --access-logfile - --error-logfile - wsgi:app
