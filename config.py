"""
配置文件 - 加载环境变量
"""
import os
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()


class Config:
    """应用配置类"""
    # Notion API 配置
    NOTION_TOKEN = os.getenv('NOTION_TOKEN', '')
    NOTION_DATABASE_ID = os.getenv('NOTION_DATABASE_ID', '')
    
    # Flask 配置
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    DEBUG = os.getenv('FLASK_DEBUG', 'True').lower() == 'true'

    # Giscus 评论（可选）
    GISCUS_REPO = os.getenv('GISCUS_REPO', '')           # 如 "owner/repo"
    GISCUS_REPO_ID = os.getenv('GISCUS_REPO_ID', '')
    GISCUS_CATEGORY = os.getenv('GISCUS_CATEGORY', '')
    GISCUS_CATEGORY_ID = os.getenv('GISCUS_CATEGORY_ID', '')
    
    @staticmethod
    def validate():
        """验证必要的配置项是否存在"""
        if not Config.NOTION_TOKEN:
            raise ValueError("NOTION_TOKEN 环境变量未设置")
        if not Config.NOTION_DATABASE_ID:
            raise ValueError("NOTION_DATABASE_ID 环境变量未设置")
        # 生产环境必须设置 SECRET_KEY
        if not Config.DEBUG and Config.SECRET_KEY == 'dev-secret-key-change-in-production':
            raise ValueError("生产环境必须设置 SECRET_KEY 环境变量")
