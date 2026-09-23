FROM python:3.12-slim

WORKDIR /srv/app

# 先装依赖，利用层缓存
# PIP_INDEX_URL 默认官方源；网络受限时可在构建时覆盖，例如：
#   docker compose build --build-arg PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ARG PIP_INDEX_URL=https://pypi.org/simple
COPY requirements.txt .
RUN pip install --no-cache-dir -i ${PIP_INDEX_URL} -r requirements.txt

# 只拷贝运行所需代码；.dockerignore 已排除 .env / tests / openspec / *.md
COPY app ./app
COPY wsgi.py entrypoint.sh ./

# 数据卷目录（由 compose 命名卷挂载）
RUN mkdir -p /data/uploads

EXPOSE 8000

# 存活探针：只探 /health，不与数据库探活混用
HEALTHCHECK --interval=10s --timeout=3s --start-period=15s --retries=5 \
    CMD python -c "import sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).status == 200 else 1)"

ENTRYPOINT ["sh", "entrypoint.sh"]
