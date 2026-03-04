"""
本地数据服务 - 从本地 JSON 文件读取 Notion 数据
"""
import json
import logging
from pathlib import Path
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

# 数据目录
DATA_DIR = Path(__file__).parent.parent / 'blog-data'
POSTS_DIR = DATA_DIR / 'posts'
METADATA_FILE = DATA_DIR / 'metadata.json'


class LocalDataService:
    """本地数据服务 - 提供与 notion_service 相同的接口"""

    @staticmethod
    def is_available() -> bool:
        """检查本地数据是否可用"""
        return METADATA_FILE.exists() and POSTS_DIR.exists()

    @staticmethod
    def get_metadata() -> Optional[Dict]:
        """获取元数据"""
        try:
            if not METADATA_FILE.exists():
                return None
            with open(METADATA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"读取元数据失败: {e}")
            return None

    @staticmethod
    def get_posts(category: Optional[str] = None) -> List[Dict]:
        """
        获取文章列表
        Args:
            category: 分类过滤（可选）
        Returns:
            文章列表
        """
        try:
            metadata = LocalDataService.get_metadata()
            if not metadata:
                logger.warning("元数据不存在，返回空列表")
                return []

            posts = []
            for post_info in metadata.get('posts', []):
                slug = post_info.get('slug')
                if not slug:
                    continue

                # 读取文章文件
                post_file = POSTS_DIR / f"{slug}.json"
                if not post_file.exists():
                    logger.warning(f"文章文件不存在: {post_file}")
                    continue

                with open(post_file, 'r', encoding='utf-8') as f:
                    post_data = json.load(f)

                # 分类过滤
                if category and post_data.get('category') != category:
                    continue

                # 转换为与 notion_service.get_posts() 相同的格式
                posts.append({
                    'title': post_data.get('title', ''),
                    'slug': post_data.get('slug', ''),
                    'date': post_data.get('date'),
                    'tags': post_data.get('tags', []),
                    'summary': post_data.get('summary', ''),
                    'category': post_data.get('category', ''),
                    'os': post_data.get('os', ''),
                    'difficulty': post_data.get('difficulty', ''),
                    'user': False,  # 本地数据暂不支持
                    'root': False,  # 本地数据暂不支持
                    'icon_type': post_data.get('icon', {}).get('type', ''),
                    'icon_url_or_emoji': post_data.get('icon', {}).get('value', ''),
                    'cover': post_data.get('cover', ''),  # 封面图
                    'status': post_data.get('status', ''),
                })

            logger.info(f"从本地读取 {len(posts)} 篇文章（分类: {category or '全部'}）")
            # 按日期降序排序（最新的在前）
            posts.sort(key=lambda x: x.get('date') or '', reverse=True)
            return posts

        except Exception as e:
            logger.error(f"读取本地文章列表失败: {e}", exc_info=True)
            return []

    @staticmethod
    def get_categories() -> List[str]:
        """获取分类列表"""
        try:
            metadata = LocalDataService.get_metadata()
            if not metadata:
                return []
            return metadata.get('categories', [])
        except Exception as e:
            logger.error(f"读取分类列表失败: {e}")
            return []

    @staticmethod
    def get_post_content(slug: str) -> Optional[Dict]:
        """
        获取单篇文章的完整内容
        Args:
            slug: 文章 slug
        Returns:
            文章数据字典，包含 content_html
        """
        try:
            post_file = POSTS_DIR / f"{slug}.json"
            if not post_file.exists():
                logger.warning(f"文章不存在: {slug}")
                return None

            with open(post_file, 'r', encoding='utf-8') as f:
                post_data = json.load(f)

            # 如果有 blocks，需要渲染为 HTML
            content_html = ''
            blocks = post_data.get('blocks', [])

            if blocks and post_data.get('status') == '已完成':
                # 导入渲染器（延迟导入避免循环依赖）
                from services.notion_service import NotionRenderer, get_notion_client

                # 使用 NotionRenderer 渲染 blocks
                # 注意：这里仍需要 notion_client，但只用于渲染，不调用 API
                notion_client = get_notion_client()
                renderer = NotionRenderer(notion_client)
                content_html = renderer.render_blocks(blocks)

            # 计算阅读时间
            from services.notion_service import calculate_reading_time
            reading_time = calculate_reading_time(content_html)

            return {
                'title': post_data.get('title', ''),
                'slug': post_data.get('slug', ''),
                'tags': post_data.get('tags', []),
                'date': post_data.get('date'),
                'summary': post_data.get('summary', ''),
                'category': post_data.get('category', ''),
                'os': post_data.get('os', ''),
                'difficulty': post_data.get('difficulty', ''),
                'user': False,
                'root': False,
                'status': post_data.get('status', ''),
                'content_html': content_html,
                'reading_time': reading_time,
            }

        except Exception as e:
            logger.error(f"读取文章内容失败 ({slug}): {e}", exc_info=True)
            return None

    @staticmethod
    def get_related_posts(current_slug: str, tags: List[str], category: str, limit: int = 3) -> List[Dict]:
        """
        获取相关文章推荐
        Args:
            current_slug: 当前文章 slug
            tags: 当前文章标签
            category: 当前文章分类
            limit: 返回数量
        Returns:
            相关文章列表
        """
        try:
            all_posts = LocalDataService.get_posts()
            if not all_posts:
                return []

            # 过滤掉当前文章
            candidates = [p for p in all_posts if p.get('slug') != current_slug]

            # 计算相似度分数
            def calculate_similarity(post):
                score = 0
                post_tags = set(post.get('tags') or [])
                current_tags = set(tags or [])

                # 标签匹配：每个匹配的标签 +2 分
                common_tags = post_tags & current_tags
                score += len(common_tags) * 2

                # 类别匹配：+1 分
                if post.get('category') == category:
                    score += 1

                return score

            # 按相似度排序
            candidates.sort(key=calculate_similarity, reverse=True)

            # 返回前 N 篇
            return candidates[:limit]

        except Exception as e:
            logger.error(f"获取相关文章失败: {e}")
            return []
