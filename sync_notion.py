"""
Notion 内容同步脚本 - 将 Notion 数据导出为本地 JSON 文件
"""
import json
import logging
import os
import sys
import hashlib
import requests
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from datetime import datetime, timezone

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.notion_service import (
    get_notion_client,
    _extract_title,
    _extract_slug,
    _extract_date,
    _extract_tags,
    _extract_summary,
    _extract_category,
    _extract_os,
    _extract_difficulty,
    _extract_status,
    _extract_icon,
)
from config import Config

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

# 数据存储目录
DATA_DIR = Path(__file__).parent / 'blog-data'
POSTS_DIR = DATA_DIR / 'posts'
IMAGES_DIR = DATA_DIR / 'images'
METADATA_FILE = DATA_DIR / 'metadata.json'

# 是否下载图片到本地（默认开启，避免 Notion AWS 临时链接过期）
DOWNLOAD_IMAGES = os.environ.get('DOWNLOAD_IMAGES', 'true').lower() == 'true'


class NotionBlockRenderer:
    """Notion Block 渲染器 - 将 blocks 转换为 HTML"""

    def __init__(self, notion_client):
        self.notion = notion_client

    def _fetch_page_blocks(self, block_id, depth=0, max_depth=10):
        """递归获取页面的所有 blocks"""
        if depth > max_depth:
            logger.warning(f"达到最大递归深度 {max_depth}，停止获取子 blocks")
            return []

        try:
            blocks = []
            has_more = True
            start_cursor = None

            while has_more:
                response = self.notion.blocks.children.list(
                    block_id=block_id,
                    start_cursor=start_cursor,
                    page_size=100
                )

                for block in response.get('results', []):
                    blocks.append(block)

                    # 如果 block 有子元素，递归获取
                    if block.get('has_children'):
                        children = self._fetch_page_blocks(
                            block['id'],
                            depth=depth + 1,
                            max_depth=max_depth
                        )
                        block['children'] = children

                has_more = response.get('has_more', False)
                start_cursor = response.get('next_cursor')

            return blocks
        except Exception as e:
            logger.error(f"获取 blocks 失败: {e}")
            return []


def download_image(url, images_dir):
    """
    下载图片到本地
    Args:
        url: 图片 URL
        images_dir: 图片保存目录
    Returns:
        本地图片路径（相对于 blog-data/）或原 URL（下载失败时）
    """
    if not url or not DOWNLOAD_IMAGES:
        return url

    try:
        # 生成文件名（使用 URL 的 hash）
        url_hash = hashlib.md5(url.encode()).hexdigest()
        parsed_url = urlparse(url)
        ext = os.path.splitext(parsed_url.path)[1] or '.jpg'
        filename = f"{url_hash}{ext}"
        filepath = images_dir / filename

        # 如果文件已存在，直接返回
        if filepath.exists():
            logger.debug(f"  图片已存在: {filename}")
            return f"/static/images/{filename}"

        # 下载图片
        logger.info(f"  下载图片: {filename}")
        response = requests.get(url, timeout=30, stream=True)
        response.raise_for_status()

        # 保存图片
        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        logger.info(f"  ✓ 图片已保存: {filename}")
        return f"/static/images/{filename}"

    except Exception as e:
        logger.error(f"  下载图片失败 ({url}): {e}")
        return url  # 下载失败时返回原 URL


def process_blocks_images(blocks, images_dir):
    """
    处理 blocks 中的图片，下载到本地并替换 URL
    Args:
        blocks: Notion blocks 列表
        images_dir: 图片保存目录
    """
    if not DOWNLOAD_IMAGES:
        return

    for block in blocks:
        block_type = block.get('type')

        # 处理图片 block
        if block_type == 'image':
            image_data = block.get('image', {})
            if image_data.get('type') == 'file':
                original_url = image_data.get('file', {}).get('url', '')
                if original_url:
                    local_path = download_image(original_url, images_dir)
                    image_data['file']['url'] = local_path
            elif image_data.get('type') == 'external':
                original_url = image_data.get('external', {}).get('url', '')
                if original_url:
                    local_path = download_image(original_url, images_dir)
                    image_data['external']['url'] = local_path

        # 递归处理子 blocks
        if block.get('children'):
            process_blocks_images(block['children'], images_dir)


def sync_posts(clean=True):
    """同步所有文章到本地 JSON 文件（支持增量同步）

    Args:
        clean: 是否清理不存在的文章和图片文件（默认 True）
    """
    logger.info("开始同步 Notion 内容...")

    if DOWNLOAD_IMAGES:
        logger.info("图片下载已启用")
    else:
        logger.info("图片下载已禁用（使用 Notion CDN URL）")

    # 确保目录存在
    POSTS_DIR.mkdir(parents=True, exist_ok=True)
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)

    # 初始化 Notion 客户端
    notion = get_notion_client()
    renderer = NotionBlockRenderer(notion)

    # 读取上次同步时间（用于增量同步）
    metadata_file = os.path.join(DATA_DIR, 'metadata.json')
    last_sync_time = None
    existing_posts = {}

    if os.path.exists(metadata_file):
        try:
            with open(metadata_file, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
                last_sync_time = metadata.get('last_sync_time')
                # 读取现有文章列表
                for post in metadata.get('posts', []):
                    existing_posts[post['slug']] = post
                if last_sync_time:
                    logger.info(f"上次同步时间: {last_sync_time}")
        except Exception as e:
            logger.warning(f"读取元数据失败: {e}")

    # 查询所有已完成和已锁住的文章
    try:
        query_filter = {
            "or": [
                {"property": "状态", "status": {"equals": "已完成"}},
                {"property": "状态", "status": {"equals": "已锁住"}}
            ]
        }

        # 如果有上次同步时间，只查询修改或新建的文章（增量同步）
        if last_sync_time:
            query_filter = {
                "and": [
                    query_filter,
                    {
                        "or": [
                            {"timestamp": "last_edited_time", "last_edited_time": {"on_or_after": last_sync_time}},
                            {"timestamp": "created_time", "created_time": {"on_or_after": last_sync_time}}
                        ]
                    }
                ]
            }
            logger.info("🔄 增量同步模式：只同步最近修改或新建的文章")
        else:
            logger.info("📦 全量同步模式：首次同步所有文章")

        response = notion.databases.query(
            database_id=Config.NOTION_DATABASE_ID,
            filter=query_filter,
            sorts=[{"property": "日期", "direction": "descending"}]
        )

        posts = response.get('results', [])

        if last_sync_time:
            logger.info(f"找到 {len(posts)} 篇需要更新的文章")
        else:
            logger.info(f"找到 {len(posts)} 篇文章")

        synced_posts = []
        categories = set()
        all_tags = set()

        # 如果是增量同步，从本地文件加载现有文章列表
        if last_sync_time:
            for post_file in POSTS_DIR.glob('*.json'):
                try:
                    with open(post_file, 'r', encoding='utf-8') as f:
                        post_data = json.load(f)
                        synced_posts.append({
                            'slug': post_data['slug'],
                            'title': post_data['title'],
                            'date': post_data['date'],
                            'category': post_data['category'],
                        })
                        if post_data.get('category'):
                            categories.add(post_data['category'])
                        all_tags.update(post_data.get('tags', []))
                except Exception as e:
                    logger.warning(f"读取文章文件失败 {post_file}: {e}")

        for idx, page in enumerate(posts, 1):
            try:
                properties = page.get('properties', {})

                # 提取基本信息
                title = _extract_title(properties)
                slug = _extract_slug(properties)
                date = _extract_date(properties)
                category = _extract_category(properties)
                tags = _extract_tags(properties)
                summary = _extract_summary(properties)
                status = _extract_status(properties)

                if not slug:
                    logger.warning(f"文章 '{title}' 没有 slug，跳过")
                    continue

                logger.info(f"[{idx}/{len(posts)}] 同步文章: {title} ({slug})")

                # 收集分类和标签
                if category:
                    categories.add(category)
                all_tags.update(tags)

                # 提取封面图 URL（null-safe）
                cover_url = ''
                cover = page.get('cover')
                if cover:
                    if cover.get('external'):
                        cover_url = cover.get('external', {}).get('url', '')
                    elif cover.get('file'):
                        cover_url = cover.get('file', {}).get('url', '')

                # 下载封面图（如果启用）
                if cover_url and DOWNLOAD_IMAGES:
                    logger.info(f"  下载封面图...")
                    cover_url = download_image(cover_url, IMAGES_DIR)

                # 提取图标信息
                icon_type, icon_value = _extract_icon(page)

                # 下载图标图片（如果是文件类型且启用了图片下载）
                if icon_type in ['file', 'external'] and icon_value and DOWNLOAD_IMAGES:
                    logger.info(f"  下载图标图片...")
                    icon_value = download_image(icon_value, IMAGES_DIR)

                # 构建文章数据
                post_data = {
                    'id': page['id'],
                    'title': title,
                    'slug': slug,
                    'date': date,
                    'category': category,
                    'tags': tags,
                    'summary': summary,
                    'status': status,
                    'os': _extract_os(properties),
                    'difficulty': _extract_difficulty(properties),
                    'icon': {'type': icon_type, 'value': icon_value},
                    'cover': cover_url,
                    'last_edited_time': page.get('last_edited_time', ''),
                    'created_time': page.get('created_time', ''),
                }

                # 获取文章内容 blocks（仅对已完成的文章）
                if status == '已完成':
                    logger.info(f"  获取文章内容...")
                    blocks = renderer._fetch_page_blocks(page['id'])

                    # 处理 blocks 中的图片
                    if DOWNLOAD_IMAGES:
                        logger.info(f"  处理文章图片...")
                        process_blocks_images(blocks, IMAGES_DIR)

                    post_data['blocks'] = blocks
                    logger.info(f"  获取到 {len(blocks)} 个 blocks")
                else:
                    post_data['blocks'] = []
                    logger.info(f"  文章已锁住，跳过内容获取")

                # 保存为 JSON 文件
                post_file = POSTS_DIR / f"{slug}.json"
                with open(post_file, 'w', encoding='utf-8') as f:
                    json.dump(post_data, f, ensure_ascii=False, indent=2)

                # 更新或添加到文章列表
                post_meta = {
                    'slug': slug,
                    'title': title,
                    'date': date,
                    'category': category,
                }

                # 如果是增量同步，更新现有文章；否则添加
                found = False
                if last_sync_time:
                    for i, p in enumerate(synced_posts):
                        if p['slug'] == slug:
                            synced_posts[i] = post_meta
                            found = True
                            break

                if not found:
                    synced_posts.append(post_meta)

                logger.info(f"  ✓ 已保存到 {post_file}")

            except Exception as e:
                logger.error(f"同步文章失败: {e}", exc_info=True)
                continue

        # 清理不存在的文章文件（需要 --clean 参数）
        if clean:
            valid_slugs = {post['slug'] for post in synced_posts}
            for post_file in POSTS_DIR.glob('*.json'):
                file_slug = post_file.stem
                if file_slug not in valid_slugs:
                    logger.info(f"删除旧文章文件: {post_file.name}")
                    post_file.unlink()

        # 清理未使用的图片文件（需要 --clean 参数）
        if clean and DOWNLOAD_IMAGES:
            logger.info("检查未使用的图片...")
            used_images = set()

            # 扫描所有文章，收集使用的图片
            for post_file in POSTS_DIR.glob('*.json'):
                try:
                    with open(post_file, 'r', encoding='utf-8') as f:
                        post_data = json.load(f)

                        # 检查封面图
                        cover = post_data.get('cover', '')
                        if cover and cover.startswith('/static/images/'):
                            used_images.add(cover.replace('/static/images/', ''))

                        # 检查图标
                        icon = post_data.get('icon', {})
                        if icon.get('value', '').startswith('/static/images/'):
                            used_images.add(icon['value'].replace('/static/images/', ''))

                        # 递归检查 blocks 中的图片
                        def collect_images(blocks):
                            for block in blocks:
                                if block.get('type') == 'image':
                                    img_data = block.get('image', {})
                                    url = ''
                                    if img_data.get('type') == 'file':
                                        url = img_data.get('file', {}).get('url', '')
                                    elif img_data.get('type') == 'external':
                                        url = img_data.get('external', {}).get('url', '')

                                    if url and url.startswith('/static/images/'):
                                        used_images.add(url.replace('/static/images/', ''))

                                if block.get('children'):
                                    collect_images(block['children'])

                        collect_images(post_data.get('blocks', []))
                except Exception as e:
                    logger.warning(f"扫描图片失败 {post_file}: {e}")

            # 删除未使用的图片
            deleted_count = 0
            for img_file in IMAGES_DIR.glob('*'):
                if img_file.is_file() and img_file.name not in used_images:
                    logger.info(f"  删除未使用的图片: {img_file.name}")
                    img_file.unlink()
                    deleted_count += 1

            if deleted_count > 0:
                logger.info(f"已删除 {deleted_count} 个未使用的图片")

        # 保存元数据
        current_time = datetime.now(timezone.utc).isoformat()

        # 去重并按日期排序
        unique_posts = {post['slug']: post for post in synced_posts}
        synced_posts = sorted(unique_posts.values(), key=lambda x: x.get('date') or '', reverse=True)

        metadata = {
            'last_sync': current_time,
            'last_sync_time': current_time,  # 用于增量同步
            'total_posts': len(synced_posts),
            'categories': sorted(list(categories)),
            'tags': sorted(list(all_tags)),
            'posts': synced_posts,
        }

        with open(METADATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)

        logger.info(f"\n同步完成！")
        logger.info(f"  总文章数: {len(synced_posts)}")
        logger.info(f"  分类数: {len(categories)}")
        logger.info(f"  标签数: {len(all_tags)}")
        logger.info(f"  数据目录: {DATA_DIR}")

        return True

    except Exception as e:
        logger.error(f"同步失败: {e}", exc_info=True)
        return False


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='同步 Notion 内容到本地')
    parser.add_argument('--clean', action='store_true', help='清理不存在的文章和图片文件')
    args = parser.parse_args()

    success = sync_posts(clean=args.clean)
    sys.exit(0 if success else 1)
