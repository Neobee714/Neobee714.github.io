FROM python:3.9-slim

WORKDIR /app

# 安装依赖
COPY requirements.txt .
# 加上 --no-cache-dir 减小体积，这一步你写对了
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Railway 会忽略 EXPOSE，但保留它作为文档是个好习惯
EXPOSE 5000

# [关键修改] 使用 Shell 格式让 $PORT 生效
# 注意：这里去掉了 [] 和逗号，直接写命令，这样才能读取环境变量
# 如果没有 PORT 变量，默认使用 5000
CMD gunicorn --bind 0.0.0.0:$PORT --workers 2 --threads 4 app:app