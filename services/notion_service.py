"""
Notion API 服务 - 处理与 Notion 数据库的交互
"""
import html
import logging
from notion_client import Client
from config import Config

logger = logging.getLogger(__name__)


def get_notion_client():
    """创建并返回 Notion 客户端实例"""
    Config.validate()
    return Client(auth=Config.NOTION_TOKEN)


def _extract_title(properties):
    """提取标题属性 (Extract title property)"""
    title_prop = properties.get('机器名称') or {}
    if (title_prop.get('type') or '') == 'title':
        return ''.join([t.get('plain_text', '') for t in (title_prop.get('title') or [])])
    return title_prop.get('title', '') or '无标题'


def _extract_slug(properties):
    """提取 Slug 属性 (Extract slug property)"""
    slug_prop = properties.get('Slug') or {}
    if (slug_prop.get('type') or '') == 'rich_text':
        return ''.join([t.get('plain_text', '') for t in (slug_prop.get('rich_text') or [])])
    return ''


def _extract_date(properties):
    """提取日期属性 (Extract date property)"""
    date_prop = properties.get('日期') or {}
    if (date_prop.get('type') or '') == 'date' and date_prop.get('date'):
        return date_prop.get('date', {}).get('start', '')
    return None


def _extract_tags(properties):
    """提取标签属性 (Extract tags property)"""
    tags_prop = properties.get('标签') or {}
    if (tags_prop.get('type') or '') == 'multi_select':
        return [x.get('name', '') for x in (tags_prop.get('multi_select') or [])]
    return []


def _extract_summary(properties):
    """提取简介属性 (Extract summary property)"""
    summary_prop = properties.get('简介') or {}
    if (summary_prop.get('type') or '') == 'rich_text':
        return ''.join([t.get('plain_text', '') for t in (summary_prop.get('rich_text') or [])])
    return ''


def _extract_category(properties):
    """提取类型属性 (Extract category property)"""
    category_prop = properties.get('类型') or {}
    if (category_prop.get('type') or '') == 'select' and category_prop.get('select'):
        return (category_prop.get('select') or {}).get('name', '') or ''
    return ''


def _extract_os(properties):
    """提取操作系统属性 (Extract OS property)"""
    return ((properties.get('操作系统') or {}).get('select') or {}).get('name') or ''


def _extract_difficulty(properties):
    """提取难度属性 (Extract difficulty property)"""
    return ((properties.get('难度') or {}).get('select') or {}).get('name') or ''


def _extract_status(properties):
    """提取状态属性 (Extract status property)"""
    status_prop = properties.get('状态') or {}
    if (status_prop.get('type') or '') == 'status' and status_prop.get('status'):
        return (status_prop.get('status') or {}).get('name', '') or ''
    return ''


def _extract_icon(page):
    """提取页面图标 (Extract page icon)"""
    icon_prop = page.get('icon') or {}
    icon_type = icon_prop.get('type') or ''
    icon_val = ''
    if icon_type == 'emoji':
        icon_val = icon_prop.get('emoji') or ''
    elif icon_type == 'external':
        icon_val = (icon_prop.get('external') or {}).get('url') or ''
    elif icon_type == 'file':
        icon_val = (icon_prop.get('file') or {}).get('url') or ''
    return icon_type, icon_val


def calculate_reading_time(content_html):
    """
    计算阅读时间（分钟）(Calculate reading time in minutes)
    假设中文阅读速度：300字/分钟，英文：200词/分钟
    """
    if not content_html:
        return 1

    import re
    # 移除 HTML 标签
    text = re.sub(r'<[^>]+>', '', content_html)
    # 移除多余空白
    text = re.sub(r'\s+', ' ', text).strip()

    # 统计中文字符数
    chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
    # 统计英文单词数
    english_words = len(re.findall(r'\b[a-zA-Z]+\b', text))

    # 计算阅读时间（分钟）
    reading_time = (chinese_chars / 300) + (english_words / 200)

    # 至少1分钟
    return max(1, round(reading_time))


def get_posts(category=None):
    """
    从 Notion Database 获取状态为「已完成」或「已锁住」的文章（中文列名）。
    返回: list 每项为 dict，键：title, slug, date, tags, os, difficulty, user, root, status。
    """
    notion = get_notion_client()
    try:
        logger.info(f"正在查询 Notion 数据库，分类: {category or '全部'}")
        # 构建 filter：筛选状态为 已完成 或 已锁住，若传入 category 则追加类型筛选
        base_filter = {
            "or": [
                {"property": "状态", "status": {"equals": "已完成"}},
                {"property": "状态", "status": {"equals": "已锁住"}}
            ]
        }
        if category:
            query_filter = {"and": [base_filter, {"property": "类型", "select": {"equals": category}}]}
        else:
            query_filter = base_filter
        response = notion.databases.query(
            database_id=Config.NOTION_DATABASE_ID,
            filter=query_filter,
            sorts=[{"property": "日期", "direction": "descending"}]
        )
        results = response.get('results', [])
        logger.info(f"查询到 {len(results)} 条记录")
        posts = []
        for page in response.get('results', []):
            properties = page.get('properties') or {}

            # 使用提取函数获取所有属性
            icon_type, icon_val = _extract_icon(page)

            posts.append({
                'title': _extract_title(properties),
                'slug': _extract_slug(properties),
                'date': _extract_date(properties),
                'tags': _extract_tags(properties),
                'summary': _extract_summary(properties),
                'category': _extract_category(properties),
                'os': _extract_os(properties),
                'difficulty': _extract_difficulty(properties),
                'user': (properties.get('user') or {}).get('checkbox', False),
                'root': (properties.get('root') or {}).get('checkbox', False),
                'icon_type': icon_type,
                'icon_url_or_emoji': icon_val,
                'status': _extract_status(properties),
            })
        logger.info(f"成功解析 {len(posts)} 篇文章")
        return posts
    except Exception as e:
        logger.error(f"获取 Notion 文章失败: {str(e)}", exc_info=True)
        raise Exception(f"获取 Notion 文章失败: {str(e)}")


def get_categories():
    """
    读取 Notion 数据库 schema，返回 properties['类型']['select']['options'] 的 name 列表。
    返回: list of str
    """
    notion = get_notion_client()
    try:
        resp = notion.databases.retrieve(database_id=Config.NOTION_DATABASE_ID)
        props = resp.get('properties') or {}
        type_prop = props.get('类型') or {}
        select_def = type_prop.get('select') or {}
        options = select_def.get('options') or []
        return [o.get('name') for o in options if o.get('name')]
    except Exception as e:
        # 返回空列表以防页面渲染中断
        return []


def _rich_text_to_html(rich_text_list):
    """将 Notion rich_text 数组转为内联 HTML（支持粗体、斜体、代码、删除线、下划线、链接等）。"""
    if not rich_text_list:
        return ''
    parts = []
    for span in rich_text_list:
        text = html.escape(span.get('plain_text', ''))
        if not text:
            continue
        annotations = span.get('annotations', {}) or {}

        # 内联代码块（优先级最高）
        if annotations.get('code'):
            parts.append(f'<code class="bg-base-300 px-1 rounded text-sm font-mono text-error">{text}</code>')
        else:
            # 应用文本样式
            if annotations.get('bold'):
                text = f'<strong>{text}</strong>'
            if annotations.get('italic'):
                text = f'<em>{text}</em>'
            if annotations.get('strikethrough'):
                text = f'<del>{text}</del>'
            if annotations.get('underline'):
                text = f'<u>{text}</u>'

            # 链接（最外层）
            link = span.get('href')
            if link:
                text = f'<a href="{html.escape(link)}" class="link link-primary" target="_blank" rel="noopener">{text}</a>'

            parts.append(text)
    return ''.join(parts)


class NotionRenderer:
    """将 Notion Block 列表转换为 HTML。"""

    SUPPORTED_TYPES = {
        'heading_1', 'heading_2', 'heading_3',
        'paragraph', 'bulleted_list_item', 'numbered_list_item',
        'quote', 'callout', 'divider', 'to_do', 'toggle', 'bookmark',
        'image', 'code'
    }

    def __init__(self, notion_client):
        self.notion = notion_client

    def _get_rich_text(self, block, key='rich_text'):
        """从 block 的 type 下取 rich_text 或 title（heading 用 title）。"""
        # Notion API: heading_1/2/3 用 "rich_text"，旧版有的用 "text"，统一取 rich_text
        payload = block or {}
        rt = payload.get(key) or payload.get('rich_text') or payload.get('text') or []
        return _rich_text_to_html(rt) if isinstance(rt, list) else html.escape(str(rt))

    def _fetch_children(self, block_id):
        """递归获取某 block 下的所有子 block（扁平顺序，深度优先）。"""
        result = []
        cursor = None
        api_calls = 0
        while True:
            api_calls += 1
            resp = self.notion.blocks.children.list(block_id=block_id, page_size=100, start_cursor=cursor)
            blocks = resp.get('results', [])
            for b in blocks:
                result.append(b)
                if b.get('has_children'):
                    child_blocks, child_calls = self._fetch_children(b['id'])
                    result.extend(child_blocks)
                    api_calls += child_calls
            cursor = resp.get('next_cursor')
            if not cursor:
                break
        return result, api_calls

    def _fetch_page_blocks(self, page_id):
        """获取页面下所有顶层 block，并递归展开有子节点的 block。"""
        import time
        start_time = time.time()
        blocks = []
        cursor = None
        api_calls = 0

        while True:
            api_calls += 1
            resp = self.notion.blocks.children.list(block_id=page_id, page_size=100, start_cursor=cursor)
            for b in resp.get('results', []):
                blocks.append(b)
                if b.get('has_children'):
                    child_blocks, child_calls = self._fetch_children(b['id'])
                    blocks.extend(child_blocks)
                    api_calls += child_calls
            cursor = resp.get('next_cursor')
            if not cursor:
                break

        elapsed = time.time() - start_time
        logger.info(f"获取 blocks 完成: {len(blocks)} 个 blocks, {api_calls} 次 API 调用, 耗时 {elapsed:.2f} 秒")
        return blocks

    def render_block(self, block):
        """将单个 block 转为 HTML。"""
        block_type = block.get('type') or ''
        if block_type not in self.SUPPORTED_TYPES:
            return ''

        block_id = block.get('id', '')
        payload = block.get(block_type) or {}

        # 标题
        if block_type == 'heading_1':
            text = self._get_rich_text(payload)
            return f'<h1 class="text-3xl font-bold mt-8 mb-4 text-base-content" id="h-{block_id[:8]}">{text}</h1>' if text else ''
        if block_type == 'heading_2':
            text = self._get_rich_text(payload)
            return f'<h2 class="text-2xl font-bold mt-6 mb-3 text-base-content" id="h-{block_id[:8]}">{text}</h2>' if text else ''
        if block_type == 'heading_3':
            text = self._get_rich_text(payload)
            return f'<h3 class="text-xl font-semibold mt-4 mb-2 text-base-content" id="h-{block_id[:8]}">{text}</h3>' if text else ''

        # 段落
        if block_type == 'paragraph':
            text = self._get_rich_text(payload)
            return f'<p class="my-2 text-base-content/90 leading-relaxed">{text}</p>' if text else '<p class="my-2">&nbsp;</p>'

        # 列表项（单个，稍后会被合并）
        if block_type == 'bulleted_list_item':
            text = self._get_rich_text(payload)
            return f'<li class="ml-4 my-1 text-base-content/90">{text}</li>' if text else ''

        if block_type == 'numbered_list_item':
            text = self._get_rich_text(payload)
            return f'<li class="ml-4 my-1 text-base-content/90">{text}</li>' if text else ''

        # 引用块
        if block_type == 'quote':
            text = self._get_rich_text(payload)
            return f'<blockquote class="border-l-4 border-primary pl-4 py-2 my-4 bg-base-200/50 italic text-base-content/80">{text}</blockquote>' if text else ''

        # 标注/提示框
        if block_type == 'callout':
            icon = (payload.get('icon') or {}).get('emoji', '💡')
            text = self._get_rich_text(payload)
            return f'<div class="alert shadow-lg my-4 bg-base-200"><span class="text-2xl">{html.escape(icon)}</span><span class="text-base-content/90">{text}</span></div>' if text else ''

        # 分割线
        if block_type == 'divider':
            return '<hr class="my-8 border-base-300">'

        # 待办事项
        if block_type == 'to_do':
            checked = payload.get('checked', False)
            text = self._get_rich_text(payload)
            checked_attr = 'checked' if checked else ''
            text_class = 'line-through text-base-content/50' if checked else 'text-base-content/90'
            return f'<div class="flex items-start gap-2 my-1"><input type="checkbox" class="checkbox checkbox-sm mt-1" disabled {checked_attr}><span class="{text_class}">{text}</span></div>' if text else ''

        # 折叠列表
        if block_type == 'toggle':
            summary_text = self._get_rich_text(payload)
            # 注意：toggle 的子内容需要在 render_blocks 中特殊处理
            # 这里只渲染摘要部分，子内容会在后续处理
            return f'<details class="collapse bg-base-200 my-4"><summary class="collapse-title text-base font-medium cursor-pointer">{summary_text}</summary><div class="collapse-content" data-toggle-id="{block_id}"></div></details>' if summary_text else ''

        # 网页书签
        if block_type == 'bookmark':
            url = payload.get('url', '')
            caption = payload.get('caption', [])
            caption_text = ''.join([c.get('plain_text', '') for c in caption]) if caption else url
            if url:
                return f'<a href="{html.escape(url)}" class="card bg-base-200 border border-base-300 p-4 my-4 block hover:border-primary transition-colors" target="_blank" rel="noopener"><div class="flex items-center gap-2"><i class="fa-solid fa-bookmark text-primary"></i><span class="text-base-content/90 break-all">{html.escape(caption_text)}</span></div></a>'
            return ''

        # 图片
        if block_type == 'image':
            url = None
            if payload.get('external') and payload['external'].get('url'):
                url = payload['external']['url']
            elif payload.get('file') and payload['file'].get('url'):
                url = payload['file']['url']
            if not url:
                return ''
            caption = (payload.get('caption') or [])
            cap_text = ''.join([c.get('plain_text', '') for c in caption]) if caption else ''
            cap_html = f'<figcaption class="text-sm text-base-content/60 mt-1">{html.escape(cap_text)}</figcaption>' if cap_text else ''
            return f'<figure class="my-4"><img src="{html.escape(url)}" alt="{html.escape(cap_text) or "image"}" class="rounded-lg max-w-full h-auto" loading="lazy"/>{cap_html}</figure>'

        # 代码块
        if block_type == 'code':
            lang = (payload.get('language') or 'plain text').strip().lower()
            # 映射 Notion 语言到 Prism/Highlight.js 的 language-xxx
            lang_map = {'plain text': 'plaintext', 'plain': 'plaintext'}
            lang = lang_map.get(lang, lang)
            code_content = ''.join([span.get('plain_text', '') for span in (payload.get('rich_text') or [])])
            code_escaped = html.escape(code_content)
            return f'<pre class="my-4 rounded-xl overflow-x-auto"><code class="language-{lang} font-mono text-sm">{code_escaped}</code></pre>'

        return ''

    def render_blocks(self, blocks):
        """将 block 列表转为完整 HTML，并合并连续列表项为 <ul> 或 <ol>。"""
        out = []
        i = 0
        while i < len(blocks):
            block = blocks[i]
            btype = block.get('type') or ''

            # 处理无序列表
            if btype == 'bulleted_list_item':
                ul_items = []
                while i < len(blocks) and (blocks[i].get('type') or '') == 'bulleted_list_item':
                    ul_items.append(self.render_block(blocks[i]))
                    i += 1
                combined = ''.join(ul_items)
                if combined:
                    out.append(f'<ul class="list-disc list-outside ml-6 space-y-1 my-2 text-base-content/90">{combined}</ul>')
                continue

            # 处理有序列表
            if btype == 'numbered_list_item':
                ol_items = []
                while i < len(blocks) and (blocks[i].get('type') or '') == 'numbered_list_item':
                    ol_items.append(self.render_block(blocks[i]))
                    i += 1
                combined = ''.join(ol_items)
                if combined:
                    out.append(f'<ol class="list-decimal list-outside ml-6 space-y-1 my-2 text-base-content/90">{combined}</ol>')
                continue

            html_fragment = self.render_block(block)
            if html_fragment:
                out.append(html_fragment)
            i += 1
        return '\n'.join(out)


def get_post_content(slug):
    """
    根据 slug 获取单篇文章的完整内容（含 Block 转成的 HTML）。
    先通过 slug 查到 Page ID，再拉取该页所有 Blocks 并渲染。
    返回: dict 含 title, slug, tags, date, summary, content_html；若未找到则返回 None。
    """
    logger.info(f"正在查询文章详情: {slug}")
    notion = get_notion_client()
    Config.validate()

    # 通过 Slug 查询数据库（支持 rich_text 或 title 类型）
    results = []
    for filter_slug in (
        {"property": "Slug", "rich_text": {"equals": slug}},
        {"property": "Slug", "title": {"equals": slug}},
    ):
        response = notion.databases.query(
            database_id=Config.NOTION_DATABASE_ID,
            filter=filter_slug
        )
        results = response.get('results', [])
        if results:
            logger.info(f"找到文章: {slug}")
            break
    if not results:
        logger.warning(f"文章未找到: {slug}")
        return None

    page = results[0]
    page_id = page['id']
    properties = page.get('properties', {})

    # 使用提取函数获取所有属性
    status = _extract_status(properties)
    title = _extract_title(properties)

    # 获取状态，如果是"已锁住"则不渲染完整内容
    content_html = ''
    if status != '已锁住':
        logger.info(f"正在渲染文章内容: {title}")
        renderer = NotionRenderer(notion)
        blocks = renderer._fetch_page_blocks(page_id)
        content_html = renderer.render_blocks(blocks)
    else:
        logger.info(f"文章已锁住，跳过内容渲染: {title}")

    return {
        'title': title,
        'slug': _extract_slug(properties) or slug,
        'tags': _extract_tags(properties),
        'date': _extract_date(properties) or page.get('created_time', ''),
        'summary': _extract_summary(properties),
        'category': _extract_category(properties),
        'os': _extract_os(properties),
        'difficulty': _extract_difficulty(properties),
        'user': (properties.get('user') or {}).get('checkbox', False),
        'root': (properties.get('root') or {}).get('checkbox', False),
        'status': status,
        'content_html': content_html,
        'reading_time': calculate_reading_time(content_html),
    }


def get_related_posts(current_slug, tags, category, limit=3):
    """
    获取相关文章推荐 (Get related posts recommendations)
    基于标签和类别的相似度推荐
    """
    try:
        all_posts = get_posts() or []
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
        logger.error(f"获取相关文章失败: {str(e)}", exc_info=True)
        return []


def sync_to_cache(app, cache_instance):
    """
    全量同步 Notion 数据到缓存 (Full sync Notion data to cache)
    用于后台异步刷新缓存，避免访客触发实时 API 请求

    关键修复：在应用上下文和请求上下文中使用 render_template 渲染 HTML 字符串后再存入缓存
    """
    import time
    from flask import render_template

    start_time = time.time()
    logger.info("[缓存同步] 开始全量同步 Notion 数据...")

    try:
        # 必须在 Flask 应用上下文和请求上下文中执行
        with app.app_context():
            # 创建一个测试请求上下文（用于 render_template 中的 url_for 等函数）
            with app.test_request_context('/'):
                # 1. 跳过首页缓存（暂时禁用，因为后台同步的 HTML 有问题）
                logger.info("[缓存同步] 跳过首页缓存（首页将实时渲染）")
                all_posts = get_posts()
                logger.info(f"[缓存同步] 共 {len(all_posts)} 篇文章")

                # 2. 同步每篇文章的详情页
                success_count = 0
                fail_count = 0
                for idx, post in enumerate(all_posts, 1):
                    slug = post.get('slug')
                    if not slug:
                        logger.warning(f"[缓存同步] 跳过无 slug 的文章: {post.get('title', '未知')}")
                        fail_count += 1
                        continue

                    try:
                        logger.info(f"[缓存同步] ({idx}/{len(all_posts)}) 正在同步文章: {slug}")
                        post_data = get_post_content(slug)
                        if post_data:
                            # 获取相关文章推荐
                            related = get_related_posts(
                                current_slug=slug,
                                tags=post_data.get('tags', []),
                                category=post_data.get('category', ''),
                                limit=3
                            )

                            # 渲染文章详情页 HTML
                            post_html = render_template('post.html', post=post_data, related_posts=related)
                            cache_key = f'post_{slug}'
                            cache_instance.set(cache_key, post_html, timeout=2592000)
                            success_count += 1
                            logger.info(f"[缓存同步] 文章 HTML 已缓存: {slug}")
                        else:
                            logger.warning(f"[缓存同步] 文章内容为空: {slug}")
                            fail_count += 1
                    except Exception as e:
                        logger.error(f"[缓存同步] 同步文章失败 {slug}: {str(e)}", exc_info=True)
                        fail_count += 1

                # 3. 同步归档页面
                logger.info("[缓存同步] 正在同步归档页面...")
                from collections import defaultdict
                archives_dict = defaultdict(lambda: defaultdict(list))
                for post in all_posts:
                    date_str = post.get('date') or ''
                    if date_str:
                        year = date_str[:4]
                        month = date_str[5:7]
                        archives_dict[year][month].append(post)

                archives_list = []
                for year in sorted(archives_dict.keys(), reverse=True):
                    months_data = []
                    for month in sorted(archives_dict[year].keys(), reverse=True):
                        months_data.append({
                            'month': month,
                            'posts': archives_dict[year][month]
                        })
                    archives_list.append({
                        'year': year,
                        'months': months_data
                    })

                archives_html = render_template('archives.html', archives=archives_list)
                cache_instance.set('archives_page', archives_html, timeout=2592000)
                logger.info("[缓存同步] 归档页面 HTML 已缓存")

                # 4. 同步标签页面
                logger.info("[缓存同步] 正在同步标签页面...")
                from collections import Counter
                tag_counter = Counter()
                tag_posts = defaultdict(list)
                for post in all_posts:
                    for tag in (post.get('tags') or []):
                        tag_counter[tag] += 1
                        tag_posts[tag].append(post)

                tags_list = [
                    {'name': tag, 'count': count, 'posts': tag_posts[tag]}
                    for tag, count in tag_counter.most_common()
                ]

                tags_html = render_template('tags.html', tags=tags_list)
                cache_instance.set('tags_page', tags_html, timeout=2592000)
                logger.info(f"[缓存同步] 标签页面 HTML 已缓存: {len(tags_list)} 个标签")

                # 5. 同步分类页面
                logger.info("[缓存同步] 正在同步分类页面...")
                categories = get_categories()
                for category in categories:
                    category_posts = get_posts(category=category)

                    # 渲染分类页面 HTML（复用 index.html 模板）
                    category_html = render_template('index.html', posts=category_posts)
                    cache_key = f'category_{category}'
                    cache_instance.set(cache_key, category_html, timeout=2592000)
                    logger.info(f"[缓存同步] 分类 HTML 已缓存: {category} ({len(category_posts)} 篇)")

                elapsed = time.time() - start_time
                logger.info(f"[缓存同步] ✅ 全量同步完成！耗时 {elapsed:.2f} 秒")
                logger.info(f"[缓存同步] 统计: 成功 {success_count} 篇，失败 {fail_count} 篇")

                return {
                    'success': True,
                    'total_posts': len(all_posts),
                    'success_count': success_count,
                    'fail_count': fail_count,
                    'elapsed': elapsed
                }

    except Exception as e:
        elapsed = time.time() - start_time
        logger.error(f"[缓存同步] ❌ 全量同步失败: {str(e)}", exc_info=True)
        return {
            'success': False,
            'error': str(e),
            'elapsed': elapsed
        }


