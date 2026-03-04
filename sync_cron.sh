#!/bin/bash
# Railway Cron Job - 定期同步 Notion 数据

echo "开始定期同步 Notion 数据..."
python sync_notion.py
echo "同步完成！"
