#!/bin/sh
set -e

echo "[entrypoint] creating tables if not exist..."
python -m scripts.init_db

echo "[entrypoint] starting uvicorn..."
# 让 uvicorn 保持为 PID 1，确保容器停止信号能够直接传入。
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
