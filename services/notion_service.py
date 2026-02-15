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
    """将 Notion rich_text 数组转为内联 HTML（支持粗体、斜体、代码等）。"""
    if not rich_text_list:
        return ''
    parts = []
    for span in rich_text_list:
        text = html.escape(span.get('plain_text', ''))
        if not text:
            continue
        annotations = span.get('annotations', {}) or {}
        if annotations.get('code'):
            parts.append(f'<code>{text}</code>')
        else:
            if annotations.get('bold'):
                text = f'<strong>{text}</strong>'
            if annotations.get('italic'):
                text = f'<em>{text}</em>'
            if annotations.get('strikethrough'):
                text = f'<s>{text}</s>'
            if annotations.get('underline'):
                text = f'<u>{text}</u>'
            link = span.get('href')
            if link:
                text = f'<a href="{html.escape(link)}" class="link link-hover" target="_blank" rel="noopener">{text}</a>'
            parts.append(text)
    return ''.join(parts)


class NotionRenderer:
    """将 Notion Block 列表转换为 HTML。"""

    SUPPORTED_TYPES = {'heading_1', 'heading_2', 'heading_3', 'paragraph', 'bulleted_list_item', 'image', 'code'}

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
        while True:
            resp = self.notion.blocks.children.list(block_id=block_id, page_size=100, start_cursor=cursor)
            blocks = resp.get('results', [])
            for b in blocks:
                result.append(b)
                if b.get('has_children'):
                    result.extend(self._fetch_children(b['id']))
            cursor = resp.get('next_cursor')
            if not cursor:
                break
        return result

    def _fetch_page_blocks(self, page_id):
        """获取页面下所有顶层 block，并递归展开有子节点的 block。"""
        blocks = []
        cursor = None
        while True:
            resp = self.notion.blocks.children.list(block_id=page_id, page_size=100, start_cursor=cursor)
            for b in resp.get('results', []):
                blocks.append(b)
                if b.get('has_children'):
                    blocks.extend(self._fetch_children(b['id']))
            cursor = resp.get('next_cursor')
            if not cursor:
                break
        return blocks

    def render_block(self, block):
        """将单个 block 转为 HTML。"""
        block_type = block.get('type') or ''
        if block_type not in self.SUPPORTED_TYPES:
            return ''

        block_id = block.get('id', '')
        payload = block.get(block_type) or {}

        if block_type == 'heading_1':
            text = self._get_rich_text(payload)
            return f'<h1 class="text-3xl font-bold mt-8 mb-4 text-base-content" id="h-{block_id[:8]}">{text}</h1>' if text else ''
        if block_type == 'heading_2':
            text = self._get_rich_text(payload)
            return f'<h2 class="text-2xl font-bold mt-6 mb-3 text-base-content" id="h-{block_id[:8]}">{text}</h2>' if text else ''
        if block_type == 'heading_3':
            text = self._get_rich_text(payload)
            return f'<h3 class="text-xl font-semibold mt-4 mb-2 text-base-content" id="h-{block_id[:8]}">{text}</h3>' if text else ''

        if block_type == 'paragraph':
            text = self._get_rich_text(payload)
            return f'<p class="my-2 text-base-content/90 leading-relaxed">{text}</p>' if text else '<p class="my-2">&nbsp;</p>'

        if block_type == 'bulleted_list_item':
            text = self._get_rich_text(payload)
            return f'<li class="ml-4 my-1 text-base-content/90">{text}</li>' if text else ''

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
        """将 block 列表转为完整 HTML，并合并连续列表项为 <ul>。"""
        out = []
        i = 0
        while i < len(blocks):
            block = blocks[i]
            btype = block.get('type') or ''
            if btype == 'bulleted_list_item':
                ul_items = []
                while i < len(blocks) and (blocks[i].get('type') or '') == 'bulleted_list_item':
                    ul_items.append(self.render_block(blocks[i]))
                    i += 1
                combined = ''.join(ul_items)
                if combined:
                    out.append(f'<ul class="list-disc my-2 pl-6">{combined}</ul>')
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

