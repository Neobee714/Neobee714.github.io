"""
Notion 内容同步脚本 - 将 Notion 数据导出为本地 JSON 文件
"""
import json
import logging
import os
import sys
import hashlib
import requests
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
import concurrent.futures
import threading

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.notion_service import (
    get_notion_client,
    NotionRenderer,
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
DOWNLOAD_IMAGES = os.environ.get('DOWNLOAD_IMAGES', 'false').lower() == 'true'


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


def _split_html_by_headings(content_html, max_chunk_chars=6000):
    """
    按 <h1> 和 <h2> 标签将 HTML 正文切分成多个分块。
    如果某个分块仍然超过 max_chunk_chars，则进一步按 <h3> 拆分。
    返回 chunks 列表 (每个元素是一段 HTML 字符串)。
    """
    import re
    # 按 <h1> 或 <h2> 拆分，同时保留拆分符
    parts = re.split(r'(?=<h[12]\b)', content_html)
    parts = [p for p in parts if p.strip()]

    # 如果全部内容没有任何 h1/h2，直接返回一整块
    if len(parts) <= 1 and len(content_html) <= max_chunk_chars:
        return [content_html]

    chunks = []
    current_chunk = ""
    for part in parts:
        # 如果当前累积块 + 新段 仍然在限额内，合并
        if len(current_chunk) + len(part) <= max_chunk_chars:
            current_chunk += part
        else:
            # 先推入已有内容
            if current_chunk.strip():
                chunks.append(current_chunk)
            # 如果这一段本身就超长，尝试按 <h3> 再拆一次
            if len(part) > max_chunk_chars:
                sub_parts = re.split(r'(?=<h3\b)', part)
                sub_chunk = ""
                for sp in sub_parts:
                    if len(sub_chunk) + len(sp) <= max_chunk_chars:
                        sub_chunk += sp
                    else:
                        if sub_chunk.strip():
                            chunks.append(sub_chunk)
                        sub_chunk = sp
                if sub_chunk.strip():
                    chunks.append(sub_chunk)
                current_chunk = ""
            else:
                current_chunk = part

    if current_chunk.strip():
        chunks.append(current_chunk)

    return chunks if chunks else [content_html]


def _translate_chunk(client, chunk_html, chunk_index, total_chunks):
    """
    翻译单个 HTML 分块，返回翻译后的 HTML 字符串。
    """
    import re

    system_prompt = """You are an expert technical translator. Translate the provided HTML content from Chinese to English.
CRITICAL RULES:
1. For any content inside <pre><code> tags, you MUST strictly preserve the programming language syntax, function names, and variables.
2. You are ONLY allowed to translate the inline code comments (e.g., text after //, #, /* */) and explanatory string literals inside code blocks.
3. Do not break the HTML structure. Keep all HTML tags intact.
4. Preserve all class names, IDs, and attributes.
5. For technical terms, use industry-standard English translations.

You will receive an HTML fragment inside <CONTENT> tags.
Return the English translation inside <CONTENT> tags.

<CONTENT>
...
</CONTENT>"""

    user_content = f"<CONTENT>\n{chunk_html}\n</CONTENT>"

    logger.info(f"    [AI 翻译] 翻译分块 {chunk_index}/{total_chunks} ({len(chunk_html)} 字符)...")
    response = client.chat.completions.create(
        model=Config.LLM_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ],
        temperature=0.3,
        max_tokens=16000
    )

    result_text = response.choices[0].message.content or ''

    # 提取 <CONTENT>...</CONTENT>
    content_match = re.search(r'<CONTENT>(.*?)</CONTENT>', result_text, re.DOTALL)
    if not content_match:
        # 兼容截断：没有闭合标签
        content_match = re.search(r'<CONTENT>(.*?)(?:</CONTENT>|$)', result_text, re.DOTALL | re.IGNORECASE)

    if content_match:
        translated = content_match.group(1).strip()
        if translated:
            return translated

    # 兜底：返回原文
    logger.warning(f"    [AI 翻译] 分块 {chunk_index} 提取失败，使用原文兜底。")
    return chunk_html


def execute_translation(title, summary, category, content_html):
    """
    调用 LLM 执行翻译，返回翻译后的字典。
    对于长文章，使用分块翻译策略避免因 token 超限导致输出截断。
    """
    if not Config.LLM_API_KEY:
        logger.warning("  未配置 LLM_API_KEY，跳过翻译")
        return None

    try:
        import re
        from openai import OpenAI
        client = OpenAI(
            api_key=Config.LLM_API_KEY,
            base_url=Config.LLM_BASE_URL
        )

        # ====== 第一步：翻译标题、摘要、分类（轻量调用） ======
        meta_prompt = """You are an expert technical translator. Translate the provided metadata from Chinese to English.
Return the English translation in the EXACT SAME delimiter format:
<TITLE>
...
</TITLE>
<SUMMARY>
...
</SUMMARY>
<CATEGORY>
...
</CATEGORY>"""

        meta_input = f"<TITLE>\n{title}\n</TITLE>\n<SUMMARY>\n{summary}\n</SUMMARY>\n<CATEGORY>\n{category}\n</CATEGORY>"

        logger.info(f"  [AI 翻译] 翻译元数据（标题/摘要/分类）: {Config.LLM_MODEL} ...")
        meta_response = client.chat.completions.create(
            model=Config.LLM_MODEL,
            messages=[
                {"role": "system", "content": meta_prompt},
                {"role": "user", "content": meta_input}
            ],
            temperature=0.3,
            max_tokens=2000
        )

        meta_text = meta_response.choices[0].message.content or ''
        title_match = re.search(r'<TITLE>(.*?)</TITLE>', meta_text, re.DOTALL)
        summary_match = re.search(r'<SUMMARY>(.*?)</SUMMARY>', meta_text, re.DOTALL)
        category_match = re.search(r'<CATEGORY>(.*?)</CATEGORY>', meta_text, re.DOTALL)

        title_en = title_match.group(1).strip() if title_match else title
        summary_en = summary_match.group(1).strip() if summary_match else summary
        category_en = category_match.group(1).strip() if category_match else category

        # ====== 第二步：分块翻译正文 HTML ======
        chunks = _split_html_by_headings(content_html, max_chunk_chars=12000)
        total_chunks = len(chunks)

        if total_chunks == 1:
            logger.info(f"  [AI 翻译] 正文较短（{len(content_html)} 字符），单次翻译...")
        else:
            logger.info(f"  [AI 翻译] 正文较长（{len(content_html)} 字符），已拆分为 {total_chunks} 个分块翻译...")

        translated_chunks = []
        for i, chunk in enumerate(chunks, 1):
            translated = _translate_chunk(client, chunk, i, total_chunks)
            translated_chunks.append(translated)

        content_en_html = '\n'.join(translated_chunks)

        logger.info(f"  ✓ [AI 翻译] 全部完成 ({total_chunks} 个分块)")

        return {
            'title_en': title_en,
            'summary_en': summary_en,
            'category_en': category_en,
            'content_en_html': content_en_html
        }
    except Exception as e:
        logger.error(f"  [AI 翻译] 失败: {e}")
        return None

def sync_posts(clean=True, skip_translate=False):
    """同步所有文章到本地 JSON 文件（支持增量同步）

    Args:
        clean: 是否清理不存在的文章和图片文件（默认 True）
        skip_translate: 是否跳过 AI 翻译（默认 False）
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

        # 直接全量查询文章列表（只获取元数据，很快），并在本地进行增量和完整性比对
        logger.info("🔄 查询 Notion 文章列表进行比对...")
        
        posts = []
        has_more = True
        next_cursor = None
        
        while has_more:
            kwargs = {
                "database_id": Config.NOTION_DATABASE_ID,
                "filter": query_filter,
                "sorts": [{"property": "日期", "direction": "descending"}]
            }
            if next_cursor:
                kwargs["start_cursor"] = next_cursor
                
            response = notion.databases.query(**kwargs)
            posts.extend(response.get('results', []))
            
            has_more = response.get('has_more', False)
            next_cursor = response.get('next_cursor')

        logger.info(f"找到 {len(posts)} 篇文章，开始比对本地完整性...")

        if last_sync_time:
            logger.info(f"找到 {len(posts)} 篇需要更新的文章")
        else:
            logger.info(f"找到 {len(posts)} 篇文章")

        synced_posts = []
        categories = set()
        all_tags = set()

        # 始终加载本地文件列表，以预填 synced_posts 及缓存信息
        for post_file in POSTS_DIR.glob('*.json'):
            try:
                with open(post_file, 'r', encoding='utf-8') as f:
                    post_data = json.load(f)
                    synced_posts.append({
                        'slug': post_data['slug'],
                        'title': post_data['title'],
                        'title_en': post_data.get('title_en', ''),
                        'date': post_data['date'],
                        'category': post_data['category'],
                        'category_en': post_data.get('category_en', ''),
                        'tags': post_data.get('tags', []),
                        'summary': post_data.get('summary', ''),
                        'summary_en': post_data.get('summary_en', ''),
                        'icon': post_data.get('icon', {'type': 'emoji', 'value': '📝'}),
                        'cover': post_data.get('cover', ''),
                        'status': post_data.get('status', '已完成'),
                    })
                    if post_data.get('category'):
                        categories.add(post_data['category'])
                    all_tags.update(post_data.get('tags', []))
            except Exception as e:
                logger.warning(f"读取文章文件失败 {post_file}: {e}")

        total_posts = len(posts)
        notion_api_semaphore = threading.Semaphore(2)

        def process_single_page(idx, page):
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
                    return None

                # ===============================
                # 完整性检测与增量跳过逻辑 (Integrity & Incremental Sync Check)
                # ===============================
                needs_sync = False
                sync_reason = ""
                post_file = POSTS_DIR / f"{slug}.json"
                notion_last_edited = page.get('last_edited_time', '')
                
                # 记录具体缺失了什么，以实现局部免拉取的“模块化修复”
                missing_translation = False
                missing_content = False
                missing_images = False
                local_data = None
                
                if not post_file.exists():
                    needs_sync = True
                    sync_reason = "本地文件缺失"
                    missing_content = True
                    missing_translation = True
                    missing_images = True
                else:
                    try:
                        with open(post_file, 'r', encoding='utf-8') as f:
                            local_data = json.load(f)
                            
                        local_last_edited = local_data.get('last_edited_time', '')
                        
                        if notion_last_edited != local_last_edited:
                            needs_sync = True
                            sync_reason = "Notion有更新"
                            missing_content = True
                            missing_translation = True
                            missing_images = True
                        elif status == '已完成':
                            # 开始完整性模块检测
                            if not local_data.get('content_html'):
                                needs_sync = True
                                missing_content = True
                                sync_reason = "缺少本地正文"
                                
                            if not skip_translate and not local_data.get('content_en_html'):
                                needs_sync = True
                                missing_translation = True
                                sync_reason = (sync_reason + "及" if sync_reason else "") + "缺少英文翻译"
                                
                            # 封面图独立检测 (如果启用了图片下载，但本地记录的 cover 不是本地路径且 Notion 有 cover)
                            if DOWNLOAD_IMAGES:
                                cover_data = page.get('cover')
                                if cover_data:
                                    local_cover = local_data.get('cover', '')
                                    if not local_cover.startswith('/static/images/'):
                                        needs_sync = True
                                        missing_images = True
                                        sync_reason = (sync_reason + "及" if sync_reason else "") + "封面图未离线"
                                        
                                icon_data = page.get('icon')
                                if icon_data and icon_data.get('type') in ['file', 'external']:
                                    local_icon = local_data.get('icon', {}).get('value', '')
                                    if not local_icon.startswith('/static/images/'):
                                        needs_sync = True
                                        missing_images = True
                                        sync_reason = (sync_reason + "及" if sync_reason else "") + "图标未离线"
                                        
                    except Exception as e:
                        needs_sync = True
                        sync_reason = "读取本地数据损坏"
                        missing_content = True
                        missing_translation = True
                        missing_images = True
                        local_data = None

                if not needs_sync:
                    # 如果这篇不需要更新，跳过大模型获取等耗时操作
                    return None
                
                logger.info(f"[{idx}/{total_posts}] 同步文章: {title} ({slug}) - 触发同步原因: {sync_reason}")

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
                    logger.info(f"  [{title}] 下载封面图...")
                    cover_url = download_image(cover_url, IMAGES_DIR)

                # 提取图标信息
                icon_type, icon_value = _extract_icon(page)

                # 下载图标图片（如果是文件类型且启用了图片下载）
                if icon_type in ['file', 'external'] and icon_value and DOWNLOAD_IMAGES:
                    logger.info(f"  [{title}] 下载图标图片...")
                    icon_value = download_image(icon_value, IMAGES_DIR)

                # 构建文章数据 (预填本地已存在且无须更新的数据)
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

                if local_data is not None:
                    if not missing_content:
                        post_data['blocks'] = local_data.get('blocks', [])
                        post_data['content_html'] = local_data.get('content_html', '')
                        
                    post_data['title_en'] = local_data.get('title_en', '')
                    post_data['summary_en'] = local_data.get('summary_en', '')
                    post_data['category_en'] = local_data.get('category_en', '')
                    post_data['content_en_html'] = local_data.get('content_en_html', '')

                # 获取文章内容 blocks（仅对已完成的文章）
                if status == '已完成':
                    if missing_content or missing_images:
                        logger.info(f"  [{title}] 获取文章内容 (Notion API)...")
                        with notion_api_semaphore:
                            blocks = renderer._fetch_page_blocks(page['id'])

                        # 处理 blocks 中的图片
                        if DOWNLOAD_IMAGES:
                            logger.info(f"  [{title}] 处理文章图片...")
                            process_blocks_images(blocks, IMAGES_DIR)

                        post_data['blocks'] = blocks
                        logger.info(f"  [{title}] 获取到 {len(blocks)} 个 blocks")
                        
                        # 生成供翻译的原始内容 HTML
                        html_renderer = NotionRenderer(notion)
                        content_html = html_renderer.render_blocks(blocks)
                        post_data['content_html'] = content_html  # 保存一份原版HTML以提高性能
                    else:
                        logger.info(f"  [{title}] 检测到本地有完整正文和图片，跳过 Notion API 获取...")
                        content_html = post_data.get('content_html', '')

                    # 执行翻译逻辑
                    if missing_translation and not skip_translate:
                        translation = execute_translation(title, summary, category, content_html)
                        if translation:
                            post_data['title_en'] = translation.get('title_en', title)
                            post_data['summary_en'] = translation.get('summary_en', summary)
                            post_data['category_en'] = translation.get('category_en', category)
                            post_data['content_en_html'] = translation.get('content_en_html', '')
                            logger.info(f"  ✓ [{title}] AI 翻译成功完成")
                        else:
                            logger.warning(f"  ⚠ [{title}] AI 翻译未返回结果或发生错误")
                    elif not missing_translation:
                        logger.info(f"  ✓ [{title}] 本地已有翻译，跳过 AI 调用")
                    else:
                        logger.info(f"  [{title}] 跳过 AI 翻译 (--skip-translate)")

                else:
                    post_data['blocks'] = []
                    logger.info(f"  [{title}] 文章已锁住，跳过内容获取/翻译")

                # 保存为 JSON 文件
                with open(post_file, 'w', encoding='utf-8') as f:
                    json.dump(post_data, f, ensure_ascii=False, indent=2)

                # 更新或添加到文章列表 (包含完整元数据以支撑高性能列表展示)
                post_meta = {
                    'slug': slug,
                    'title': post_data.get('title', title),
                    'title_en': post_data.get('title_en', ''),
                    'date': date,
                    'category': post_data.get('category', category),
                    'category_en': post_data.get('category_en', ''),
                    'tags': tags,
                    'summary': post_data.get('summary', summary),
                    'summary_en': post_data.get('summary_en', ''),
                    'icon': {'type': icon_type, 'value': icon_value},
                    'cover': cover_url,
                    'status': status
                }

                logger.info(f"  ✓ [{title}] 已保存到 {post_file}")
                return post_meta

            except Exception as e:
                logger.error(f"同步文章失败 [{idx}/{total_posts}]: {e}", exc_info=True)
                return None

        logger.info(f"🚀 开始多线程处理 {total_posts} 篇文章 (最大并发: 5)...")
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(process_single_page, idx, page) for idx, page in enumerate(posts, 1)]
            for future in concurrent.futures.as_completed(futures):
                post_meta = future.result()
                if post_meta:
                    if post_meta.get('category'):
                        categories.add(post_meta['category'])
                    all_tags.update(post_meta.get('tags', []))
                    
                    found = False
                    for i, p in enumerate(synced_posts):
                        if p['slug'] == post_meta['slug']:
                            synced_posts[i] = post_meta
                            found = True
                            break
                    if not found:
                        synced_posts.append(post_meta)

        # 清理不存在的文章文件（需要 --clean 参数）
        if clean:
            valid_slugs = { _extract_slug(post.get('properties', {})) for post in posts }
            valid_slugs.discard('')
            for post_file in POSTS_DIR.glob('*.json'):
                file_slug = post_file.stem
                if file_slug not in valid_slugs:
                    logger.info(f"删除旧文章文件: {post_file.name}")
                    post_file.unlink()
                    
            synced_posts = [p for p in synced_posts if p['slug'] in valid_slugs]

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
    parser.add_argument('--skip-translate', action='store_true', help='跳过文章的 AI 翻译过程，加速同步（适用于首次全量获取或快速更新）')
    args = parser.parse_args()

    success = sync_posts(clean=args.clean, skip_translate=args.skip_translate)
    sys.exit(0 if success else 1)
