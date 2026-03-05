FROM python:3.9-slim

WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5000

# 使用 start.sh 脚本（先同步数据，再启动服务）
CMD ["bash", "start.sh"]
