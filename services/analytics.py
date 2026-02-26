"""
访问量统计模块 (Analytics Module)
使用 SQLite 存储访问记录
"""
import sqlite3
import os
import logging
from datetime import datetime, timedelta
from threading import Lock

logger = logging.getLogger(__name__)

class Analytics:
    def __init__(self, db_path='analytics.db'):
        self.db_path = db_path
        self.lock = Lock()
        self._init_db()
    
    def _init_db(self):
        """初始化数据库表"""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 页面访问记录表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS page_views (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    path TEXT NOT NULL,
                    ip TEXT,
                    user_agent TEXT,
                    referer TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # 创建索引
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_path ON page_views(path)
            ''')
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_timestamp ON page_views(timestamp)
            ''')
            
            # 文章访问统计表（聚合数据）
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS post_stats (
                    slug TEXT PRIMARY KEY,
                    total_views INTEGER DEFAULT 0,
                    unique_ips INTEGER DEFAULT 0,
                    last_viewed DATETIME
                )
            ''')
            
            conn.commit()
            conn.close()
    
    def record_view(self, path, ip=None, user_agent=None, referer=None):
        """记录一次页面访问"""
        with self.lock:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                
                cursor.execute('''
                    INSERT INTO page_views (path, ip, user_agent, referer)
                    VALUES (?, ?, ?, ?)
                ''', (path, ip, user_agent, referer))
                
                # 如果是文章页面，更新统计
                if path.startswith('/post/'):
                    slug = path.replace('/post/', '')
                    
                    # 获取该文章的唯一IP数
                    cursor.execute('''
                        SELECT COUNT(DISTINCT ip) FROM page_views
                        WHERE path = ? AND ip IS NOT NULL
                    ''', (path,))
                    unique_ips = cursor.fetchone()[0]
                    
                    # 更新或插入统计
                    cursor.execute('''
                        INSERT INTO post_stats (slug, total_views, unique_ips, last_viewed)
                        VALUES (?, 1, ?, CURRENT_TIMESTAMP)
                        ON CONFLICT(slug) DO UPDATE SET
                            total_views = total_views + 1,
                            unique_ips = ?,
                            last_viewed = CURRENT_TIMESTAMP
                    ''', (slug, unique_ips, unique_ips))
                
                conn.commit()
                conn.close()
            except Exception as e:
                logger.error(f"记录访问失败: {e}", exc_info=True)
    
    def get_post_views(self, slug):
        """获取文章访问量"""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT total_views, unique_ips FROM post_stats WHERE slug = ?
            ''', (slug,))
            
            result = cursor.fetchone()
            conn.close()
            
            if result:
                return {'total_views': result[0], 'unique_ips': result[1]}
            return {'total_views': 0, 'unique_ips': 0}
    
    def get_top_posts(self, limit=10):
        """获取访问量最高的文章"""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT slug, total_views, unique_ips, last_viewed
                FROM post_stats
                ORDER BY total_views DESC
                LIMIT ?
            ''', (limit,))
            
            results = cursor.fetchall()
            conn.close()
            
            return [
                {
                    'slug': row[0],
                    'total_views': row[1],
                    'unique_ips': row[2],
                    'last_viewed': row[3]
                }
                for row in results
            ]
    
    def get_stats_summary(self):
        """获取统计摘要"""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 总访问量
            cursor.execute('SELECT COUNT(*) FROM page_views')
            total_views = cursor.fetchone()[0]
            
            # 今日访问量
            cursor.execute('''
                SELECT COUNT(*) FROM page_views
                WHERE DATE(timestamp) = DATE('now')
            ''')
            today_views = cursor.fetchone()[0]
            
            # 昨日访问量
            cursor.execute('''
                SELECT COUNT(*) FROM page_views
                WHERE DATE(timestamp) = DATE('now', '-1 day')
            ''')
            yesterday_views = cursor.fetchone()[0]
            
            # 本周访问量
            cursor.execute('''
                SELECT COUNT(*) FROM page_views
                WHERE timestamp >= DATE('now', '-7 days')
            ''')
            week_views = cursor.fetchone()[0]
            
            # 本月访问量
            cursor.execute('''
                SELECT COUNT(*) FROM page_views
                WHERE timestamp >= DATE('now', 'start of month')
            ''')
            month_views = cursor.fetchone()[0]
            
            # 独立访客数（总）
            cursor.execute('SELECT COUNT(DISTINCT ip) FROM page_views WHERE ip IS NOT NULL')
            unique_visitors = cursor.fetchone()[0]
            
            # 今日独立访客
            cursor.execute('''
                SELECT COUNT(DISTINCT ip) FROM page_views
                WHERE DATE(timestamp) = DATE('now') AND ip IS NOT NULL
            ''')
            today_unique = cursor.fetchone()[0]
            
            # 文章总数
            cursor.execute('SELECT COUNT(*) FROM post_stats')
            total_posts = cursor.fetchone()[0]
            
            conn.close()
            
            return {
                'total_views': total_views,
                'today_views': today_views,
                'yesterday_views': yesterday_views,
                'week_views': week_views,
                'month_views': month_views,
                'unique_visitors': unique_visitors,
                'today_unique': today_unique,
                'total_posts': total_posts
            }
    
    def get_recent_views(self, limit=50):
        """获取最近访问记录"""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT path, ip, user_agent, referer, timestamp
                FROM page_views
                ORDER BY timestamp DESC
                LIMIT ?
            ''', (limit,))
            
            results = cursor.fetchall()
            conn.close()
            
            return [
                {
                    'path': row[0],
                    'ip': row[1],
                    'user_agent': row[2],
                    'referer': row[3],
                    'timestamp': row[4]
                }
                for row in results
            ]
    
    def get_daily_stats(self, days=30):
        """获取每日统计数据（用于图表）"""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT DATE(timestamp) as date, COUNT(*) as views
                FROM page_views
                WHERE timestamp >= DATE('now', ? || ' days')
                GROUP BY DATE(timestamp)
                ORDER BY date DESC
            ''', (f'-{days}',))
            
            results = cursor.fetchall()
            conn.close()
            
            return [
                {'date': row[0], 'views': row[1]}
                for row in results
            ]
