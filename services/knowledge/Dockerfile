FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple

WORKDIR /code

COPY requirements.txt .
RUN pip install -r requirements.txt

# 将分词器词表打包进镜像，避免文档入库时临时下载。
ENV TIKTOKEN_CACHE_DIR=/opt/tiktoken_cache
COPY tiktoken_cache/ /opt/tiktoken_cache/

COPY app ./app
COPY scripts ./scripts
COPY entrypoint.sh .

EXPOSE 8000

ENTRYPOINT ["sh", "entrypoint.sh"]
