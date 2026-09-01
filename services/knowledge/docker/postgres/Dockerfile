FROM pgvector/pgvector:pg16

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    postgresql-server-dev-16 \
    wget \
    bzip2 \
    git \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# 1. 编译安装 SCWS 中文分词库
RUN cd /tmp \
    && wget -q http://www.xunsearch.com/scws/down/scws-1.2.3.tar.bz2 \
    && tar xjf scws-1.2.3.tar.bz2 \
    && cd scws-1.2.3 \
    && ./configure --prefix=/usr/local \
    && make -j$(nproc) \
    && make install \
    && ldconfig \
    && cd /tmp && rm -rf scws-1.2.3 scws-1.2.3.tar.bz2

# 2. 编译安装 zhparser (PG 扩展,依赖 SCWS)
RUN cd /tmp \
    && git clone https://github.com/amutu/zhparser.git \
    && cd zhparser \
    && SCWS_HOME=/usr/local make \
    && make install \
    && cd /tmp && rm -rf zhparser

COPY init-extensions.sql /docker-entrypoint-initdb.d/