"""
Notion API 服务 - 处理与 Notion 数据库的交互
"""
import html
import logging
import os
from notion_client import Client
from config import Config

logger = logging.getLogger(__name__)


def get_notion_client():
    """创建并返回 Notion 客户端实例"""
    Config.validate()
    
    # 开发环境：禁用 SSL 验证（解决代理 SSL 握手问题）
    if Config.DEBUG:
        try:
            import httpx
            # 创建不验证 SSL 的客户端
            http_client = httpx.Client(verify=False)
            logger.warning("开发模式：已禁用 SSL 验证")
            return Client(auth=Config.NOTION_TOKEN, client=http_client)
        except Exception as e:
            logger.warning(f"无法创建自定义 HTTP 客户端: {e}")
    
    # 生产环境：使用默认配置
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
    """将 Notion rich_text 数组转为内联 HTML（支持粗体、斜体、代码、删除线、下划线、链接、颜色等）。"""
    if not rich_text_list:
        return ''

    # Notion 颜色映射到 CSS 类（使用 data-* 属性实现主题自适应）
    # 通过 CSS 变量和 data-color 属性，在 CSS 中根据 data-theme 切换颜色
    COLOR_ATTRS = {
        'default': '',
        'gray': 'data-notion-color="gray"',
        'brown': 'data-notion-color="brown"',
        'orange': 'data-notion-color="orange"',
        'yellow': 'data-notion-color="yellow"',
        'green': 'data-notion-color="green"',
        'blue': 'data-notion-color="blue"',
        'purple': 'data-notion-color="purple"',
        'pink': 'data-notion-color="pink"',
        'red': 'data-notion-color="red"',
        # 背景色（_background 后缀）
        'gray_background': 'data-notion-color="gray-bg"',
        'brown_background': 'data-notion-color="brown-bg"',
        'orange_background': 'data-notion-color="orange-bg"',
        'yellow_background': 'data-notion-color="yellow-bg"',
        'green_background': 'data-notion-color="green-bg"',
        'blue_background': 'data-notion-color="blue-bg"',
        'purple_background': 'data-notion-color="purple-bg"',
        'pink_background': 'data-notion-color="pink-bg"',
        'red_background': 'data-notion-color="red-bg"',
    }

    parts = []
    for span in rich_text_list:
        text = html.escape(span.get('plain_text', ''))
        if not text:
            continue
        annotations = span.get('annotations', {}) or {}
        color = annotations.get('color', 'default')

        # 内联代码块（优先级最高，但也要支持颜色）
        if annotations.get('code'):
            # 如果内联代码同时有颜色标注，添加 data-notion-color 属性
            color_attr = COLOR_ATTRS.get(color, '')
            if color_attr:
                parts.append(f'<code class="notion-inline-code notion-text bg-base-300 px-1 rounded text-sm font-mono" {color_attr}>{text}</code>')
            else:
                parts.append(f'<code class="notion-inline-code bg-base-300 px-1 rounded text-sm font-mono">{text}</code>')
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

            # 应用颜色/背景色（使用 data 属性）
            color_attr = COLOR_ATTRS.get(color, '')
            if color_attr:
                text = f'<span class="notion-text" {color_attr}>{text}</span>'

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
        'image', 'code', 'equation', 'table', 'table_row', 'column_list', 'column',
        'table_of_contents'
    }

    def __init__(self, notion_client):
        self.notion = notion_client
        self.headings = []  # 存储所有标题用于生成目录

    def _get_rich_text(self, block, key='rich_text'):
        """从 block 的 type 下取 rich_text 或 title（heading 用 title）。"""
        # Notion API: heading_1/2/3 用 "rich_text"，旧版有的用 "text"，统一取 rich_text
        payload = block or {}
        rt = payload.get(key) or payload.get('rich_text') or payload.get('text') or []
        return _rich_text_to_html(rt) if isinstance(rt, list) else html.escape(str(rt))

    def _render_column_children(self, column_block):
        """渲染列（column）内的子块内容"""
        if not column_block.get('has_children') or 'children' not in column_block:
            return ''

        children = column_block.get('children', [])
        children_html = [self.render_block(child) for child in children]
        return ''.join(children_html)

    def _collect_headings(self, blocks):
        """递归收集所有标题块用于生成目录"""
        for block in blocks:
            block_type = block.get('type', '')
            block_id = block.get('id', '')
            payload = block.get(block_type, {})

            # 收集标题（非折叠标题）
            if block_type in ['heading_1', 'heading_2', 'heading_3']:
                is_toggleable = payload.get('is_toggleable', False)
                if not is_toggleable:  # 只收集非折叠标题
                    text = self._get_rich_text(payload)
                    if text:
                        level = int(block_type[-1])  # 提取 1, 2, 3
                        self.headings.append({'level': level, 'text': text, 'id': f"h-{block_id[:8]}"})

            # 递归处理子块
            if block.get('has_children') and 'children' in block:
                self._collect_headings(block.get('children', []))

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
                # 对于有子节点的 block，获取子内容并附加到 children 字段
                if b.get('has_children'):
                    child_blocks, child_calls = self._fetch_children(b['id'])
                    b['children'] = child_blocks  # 将子 block 附加到父 block
                    api_calls += child_calls
                    # 对于列表项和 todo，继续扁平化展开（保持原有行为）
                    if b.get('type') in ['bulleted_list_item', 'numbered_list_item', 'to_do']:
                        blocks.extend(child_blocks)
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
            is_toggleable = payload.get('is_toggleable', False)
            if is_toggleable and block.get('has_children') and 'children' in block:
                # 可折叠的一级标题
                children = block.get('children', [])
                nested_items = [self.render_block(child) for child in children]
                children_html = ''.join(nested_items) if nested_items else ''
                return f'<details class="notion-toggle my-2"><summary class="cursor-pointer py-1 px-2 hover:bg-base-200 rounded flex items-center gap-2 text-3xl font-bold"><span class="toggle-arrow">▶</span><span>{text}</span></summary><div class="ml-6 mt-1">{children_html}</div></details>' if text else ''
            return f'<h1 class="text-3xl font-bold mt-8 mb-4 text-base-content" id="h-{block_id[:8]}">{text}</h1>' if text else ''

        if block_type == 'heading_2':
            text = self._get_rich_text(payload)
            is_toggleable = payload.get('is_toggleable', False)
            if is_toggleable and block.get('has_children') and 'children' in block:
                # 可折叠的二级标题
                children = block.get('children', [])
                nested_items = [self.render_block(child) for child in children]
                children_html = ''.join(nested_items) if nested_items else ''
                return f'<details class="notion-toggle my-2"><summary class="cursor-pointer py-1 px-2 hover:bg-base-200 rounded flex items-center gap-2 text-2xl font-bold"><span class="toggle-arrow">▶</span><span>{text}</span></summary><div class="ml-6 mt-1">{children_html}</div></details>' if text else ''
            return f'<h2 class="text-2xl font-bold mt-6 mb-3 text-base-content" id="h-{block_id[:8]}">{text}</h2>' if text else ''

        if block_type == 'heading_3':
            text = self._get_rich_text(payload)
            is_toggleable = payload.get('is_toggleable', False)
            if is_toggleable and block.get('has_children') and 'children' in block:
                # 可折叠的三级标题
                children = block.get('children', [])
                nested_items = [self.render_block(child) for child in children]
                children_html = ''.join(nested_items) if nested_items else ''
                return f'<details class="notion-toggle my-2"><summary class="cursor-pointer py-1 px-2 hover:bg-base-200 rounded flex items-center gap-2 text-xl font-semibold"><span class="toggle-arrow">▶</span><span>{text}</span></summary><div class="ml-6 mt-1">{children_html}</div></details>' if text else ''
            return f'<h3 class="text-xl font-semibold mt-4 mb-2 text-base-content" id="h-{block_id[:8]}">{text}</h3>' if text else ''

        # 段落
        if block_type == 'paragraph':
            text = self._get_rich_text(payload)
            return f'<p class="my-2 text-base-content/90 leading-relaxed">{text}</p>' if text else '<p class="my-2">&nbsp;</p>'

        # 列表项（单个，稍后会被合并）
        if block_type == 'bulleted_list_item':
            text = self._get_rich_text(payload)
            # 处理嵌套子项目（二级使用空心圆）
            children_html = ''
            if block.get('has_children') and 'children' in block:
                children = block.get('children', [])
                if children:
                    nested_items = [self.render_block(child) for child in children if child.get('type') == 'bulleted_list_item']
                    if nested_items:
                        children_html = f'<ul class="list-[circle] list-outside ml-6 space-y-1 my-1">{"".join(nested_items)}</ul>'
            return f'<li class="ml-4 my-1 text-base-content/90">{text}{children_html}</li>' if text else ''

        if block_type == 'numbered_list_item':
            text = self._get_rich_text(payload)
            # 处理嵌套子项目（二级使用小写字母）
            children_html = ''
            if block.get('has_children') and 'children' in block:
                children = block.get('children', [])
                if children:
                    nested_items = [self.render_block(child) for child in children if child.get('type') == 'numbered_list_item']
                    if nested_items:
                        children_html = f'<ol class="list-[lower-alpha] list-outside ml-6 space-y-1 my-1">{"".join(nested_items)}</ol>'
            return f'<li class="ml-4 my-1 text-base-content/90">{text}{children_html}</li>' if text else ''

        # 引用块
        if block_type == 'quote':
            text = self._get_rich_text(payload)
            return f'<blockquote class="border-l-4 border-primary pl-4 py-2 my-4 bg-base-200/50 italic text-base-content/80">{text}</blockquote>' if text else ''

        # 标注/提示框
        if block_type == 'callout':
            icon = (payload.get('icon') or {}).get('emoji', '💡')
            text = self._get_rich_text(payload)
            # 获取背景色（Notion callout 支持颜色）
            color = payload.get('color', 'gray_background')
            # 使用 Notion 风格的提示框样式
            return f'<div class="notion-callout my-4 p-4 rounded-lg border-l-4 flex gap-3 items-start" data-callout-color="{color}"><span class="text-2xl flex-shrink-0">{html.escape(icon)}</span><div class="flex-1 text-base-content/90">{text}</div></div>' if text else ''

        # 分割线
        if block_type == 'divider':
            return '<hr class="my-8 border-base-300">'

        # 待办事项
        if block_type == 'to_do':
            checked = payload.get('checked', False)
            text = self._get_rich_text(payload)
            checked_attr = 'checked' if checked else ''
            text_class = 'line-through text-base-content/50' if checked else 'text-base-content/90'

            # 处理嵌套子任务
            children_html = ''
            if block.get('has_children') and 'children' in block:
                children = block.get('children', [])
                if children:
                    nested_items = [self.render_block(child) for child in children]
                    if nested_items:
                        children_html = f'<div class="ml-6 mt-1">{"".join(nested_items)}</div>'

            checkbox_html = f'<input type="checkbox" class="checkbox checkbox-sm mt-1 todo-checkbox" {checked_attr}>'
            return f'<div class="flex items-start gap-2 my-1">{checkbox_html}<div class="flex-1"><span class="todo-text {text_class}">{text}</span>{children_html}</div></div>' if text else ''

        # 折叠列表
        if block_type == 'toggle':
            summary_text = self._get_rich_text(payload)
            # 处理嵌套子内容
            children_html = ''
            if block.get('has_children') and 'children' in block:
                children = block.get('children', [])
                if children:
                    nested_items = [self.render_block(child) for child in children]
                    if nested_items:
                        children_html = ''.join(nested_items)
            # 使用 Notion 风格的折叠块样式（标题加粗）
            return f'<details class="notion-toggle my-2"><summary class="cursor-pointer py-1 px-2 hover:bg-base-200 rounded flex items-center gap-2 font-semibold"><span class="toggle-arrow">▶</span><span>{summary_text}</span></summary><div class="ml-6 mt-1">{children_html}</div></details>' if summary_text else ''

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
            # 使用 _rich_text_to_html 来支持代码块中的颜色
            code_html = _rich_text_to_html(payload.get('rich_text') or [])
            return f'<pre class="bg-base-300 text-base-content p-4 my-4 rounded-xl overflow-x-auto"><code class="language-{lang} font-mono text-sm">{code_html}</code></pre>'

        # 块级公式 (Block-level Math Equation)
        if block_type == 'equation':
            expression = payload.get('expression', '')
            if expression:
                # 使用 KaTeX 渲染 LaTeX 公式（块级显示）
                return f'<div class="notion-equation my-4 overflow-x-auto text-center"><span class="katex-block">{html.escape(expression)}</span></div>'
            return ''

        # 表格 (Table)
        if block_type == 'table':
            if not block.get('has_children') or 'children' not in block:
                return ''

            table_width = payload.get('table_width', 0)
            has_column_header = payload.get('has_column_header', False)
            has_row_header = payload.get('has_row_header', False)

            rows_html = []
            children = block.get('children', [])

            for idx, child in enumerate(children):
                if child.get('type') == 'table_row':
                    cells = child.get('table_row', {}).get('cells', [])
                    cells_html = []

                    for cell_idx, cell in enumerate(cells):
                        # cell 是 rich_text 数组
                        cell_text = _rich_text_to_html(cell)

                        # 判断是否为表头
                        is_header = (idx == 0 and has_column_header) or (cell_idx == 0 and has_row_header)
                        tag = 'th' if is_header else 'td'
                        cell_class = 'border-2 border-base-content/30 px-4 py-2 bg-base-200' if is_header else 'border-2 border-base-content/30 px-4 py-2'

                        cells_html.append(f'<{tag} class="{cell_class}">{cell_text}</{tag}>')

                    rows_html.append(f'<tr>{"".join(cells_html)}</tr>')

            table_html = f'<table class="table-auto border-collapse border-2 border-base-content/30 my-4 w-full">{"".join(rows_html)}</table>'
            return f'<div class="overflow-x-auto">{table_html}</div>'

        # 表格行 (Table Row) - 通常由 table 块处理，这里作为后备
        if block_type == 'table_row':
            return ''

        # 分栏布局 (Column List)
        if block_type == 'column_list':
            if not block.get('has_children') or 'children' not in block:
                return ''

            children = block.get('children', [])
            columns_html = []

            for child in children:
                if child.get('type') == 'column':
                    column_content = self._render_column_children(child)
                    columns_html.append(f'<div class="flex-1 px-2">{column_content}</div>')

            return f'<div class="flex gap-4 my-4">{"".join(columns_html)}</div>'

        # 单列 (Column) - 通常由 column_list 块处理，这里作为后备
        if block_type == 'column':
            return self._render_column_children(block)

        # 目录 (Table of Contents)
        if block_type == 'table_of_contents':
            # 生成目录 HTML
            if not self.headings:
                return '<div class="notion-toc my-4 p-4 bg-base-200 rounded-lg"><p class="text-base-content/70">目录将在渲染完所有标题后显示</p></div>'

            toc_items = []
            for heading in self.headings:
                level = heading['level']
                text = heading['text']
                heading_id = heading['id']
                # 根据标题级别设置缩进
                indent_class = f'ml-{(level - 1) * 4}'
                toc_items.append(f'<li class="{indent_class} my-1"><a href="#{heading_id}" class="text-primary hover:underline">{text}</a></li>')

            toc_html = f'<ul class="space-y-1">{"".join(toc_items)}</ul>'
            return f'<div class="notion-toc my-4 p-4 bg-base-200 rounded-lg"><p class="text-sm font-semibold mb-2 text-base-content">目录</p>{toc_html}</div>'

        return ''

    def render_blocks(self, blocks):
        """将 block 列表转为完整 HTML，并合并连续列表项为 <ul> 或 <ol>。"""
        # 预处理：先收集所有标题用于生成目录
        self.headings = []  # 重置标题列表
        self._collect_headings(blocks)

        out = []
        i = 0
        while i < len(blocks):
            block = blocks[i]
            btype = block.get('type') or ''

            # 处理无序列表（一级使用实心圆 disc）
            if btype == 'bulleted_list_item':
                ul_items = []
                while i < len(blocks) and (blocks[i].get('type') or '') == 'bulleted_list_item':
                    ul_items.append(self.render_block(blocks[i]))
                    i += 1
                combined = ''.join(ul_items)
                if combined:
                    out.append(f'<ul class="list-disc list-outside ml-6 space-y-1 my-2 text-base-content/90">{combined}</ul>')
                continue

            # 处理有序列表（一级使用数字 1,2,3）
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


