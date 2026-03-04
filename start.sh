#!/bin/bash
# Railway 启动脚本 - 先同步数据，再启动应用

echo "=========================================="
echo "Railway 启动流程"
echo "=========================================="

# 1. 同步 Notion 数据到本地
echo "步骤 1: 同步 Notion 数据..."
python sync_notion.py --clean

if [ $? -eq 0 ]; then
    echo "✓ 数据同步成功"
else
    echo "⚠ 数据同步失败，将使用 Notion API 作为后备"
fi

# 2. 启动 Gunicorn 服务器
echo ""
echo "步骤 2: 启动 Web 服务器..."
echo "=========================================="

exec gunicorn --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 120 app:app
