"""
Neobee's Blog - Flask 主入口文件
"""
import os
import traceback
import logging
from collections import defaultdict
from flask import Flask, render_template, abort, make_response, url_for, request
from config import Config
from services.notion_service import get_posts, get_post_content, get_categories, get_related_posts
try:
    from flask_caching import Cache  # type: ignore
except Exception:
    # Fallback dummy Cache when flask_caching is not installed (prevents import errors in dev)
    class Cache:
        def __init__(self, app=None, config=None):
            pass
        def cached(self, *a, **k):
            def deco(f):
                return f
            return deco

try:
    from flask_wtf.csrf import CSRFProtect, CSRFError, exempt as csrf_exempt  # type: ignore
except Exception:
    # Fallback dummy CSRFProtect
    class CSRFProtect:
        def __init__(self, app=None):
            pass
    class CSRFError(Exception):
        pass
    # Dummy csrf_exempt decorator
    def csrf_exempt(f):
        return f

try:
    from flask_limiter import Limiter  # type: ignore
    from flask_limiter.util import get_remote_address  # type: ignore
except Exception:
    # Fallback dummy Limiter
    class Limiter:
        def __init__(self, *a, **k):
            pass
        def limit(self, *a, **k):
            def deco(f):
                return f
            return deco
    def get_remote_address():
        return '127.0.0.1'

import pkgutil
import importlib.util

# Shim for environments where pkgutil.get_loader is missing (some custom/stripped Python builds)
if not hasattr(pkgutil, 'get_loader'):
    def _pkgutil_get_loader(name):
        # Avoid querying for __main__ which can cause importlib to rely on __spec__.
        if name == '__main__':
            return None
        try:
            spec = importlib.util.find_spec(name)
            return spec.loader if spec else None
        except Exception:
            return None
    pkgutil.get_loader = _pkgutil_get_loader

app = Flask(__name__)
app.config.from_object(Config)

# CSRF 保护 (CSRF Protection)
csrf = CSRFProtect(app)

# 速率限制 (Rate Limiting)
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"
)

# 配置日志系统
logging.basicConfig(
    level=logging.INFO if not getattr(Config, 'DEBUG', True) else logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    force=True  # 强制重新配置，覆盖之前的配置
)
logger = logging.getLogger(__name__)
# 禁用 Werkzeug 的冗长日志
logging.getLogger('werkzeug').setLevel(logging.WARNING)
# 缓存配置：开发环境使用 SimpleCache，生产可改为 FileSystemCache
if getattr(Config, 'DEBUG', True):
    cache_config = {    
        'CACHE_TYPE': 'SimpleCache',
        'CACHE_DEFAULT_TIMEOUT': 300
    }
else:
    cache_config = {
        'CACHE_TYPE': 'FileSystemCache',
        'CACHE_DIR': 'flask_cache',
        'CACHE_DEFAULT_TIMEOUT': 300
    }
cache = Cache(app, config=cache_config)

@app.context_processor
def inject_categories():
    """将 categories 注入到所有模板中（从 Notion schema 自动读取）"""
    try:
        cats = _get_cached_categories()
    except Exception:
        cats = []
    return {'categories': cats}

@cache.cached(timeout=600, key_prefix='categories')
def _get_cached_categories():
    """缓存的分类获取函数"""
    return get_categories() or []



@app.route('/')
def index():
    """首页路由：渲染文章列表（支持搜索和分页，每页 15 篇）"""
    try:
        # 获取页码参数，默认第 1 页
        page = request.args.get('page', 1, type=int)
        # 获取搜索关键词
        search_query = request.args.get('q', '').strip()
        per_page = 15  # 每页显示 15 篇文章

        logger.info(f"正在获取文章列表 - 第 {page} 页，搜索词: '{search_query}'")
        all_posts = get_posts()

        # 搜索过滤（如果有搜索关键词）
        if search_query:
            search_lower = search_query.lower()
            filtered_posts = []
            for post in all_posts:
                # 搜索标题
                if search_lower in (post.get('title') or '').lower():
                    filtered_posts.append(post)
                    continue
                # 搜索简介
                if search_lower in (post.get('summary') or '').lower():
                    filtered_posts.append(post)
                    continue
                # 搜索标签
                tags = post.get('tags') or []
                if any(search_lower in tag.lower() for tag in tags):
                    filtered_posts.append(post)
                    continue
                # 搜索分类
                if search_lower in (post.get('category') or '').lower():
                    filtered_posts.append(post)
                    continue
            all_posts = filtered_posts
            logger.info(f"搜索 '{search_query}' 找到 {len(all_posts)} 篇文章")

        total_posts = len(all_posts)
        logger.info(f"共 {total_posts} 篇文章")

        # 计算总页数
        total_pages = (total_posts + per_page - 1) // per_page if total_posts > 0 else 1

        # 确保页码在有效范围内
        if page < 1:
            page = 1
        elif page > total_pages and total_pages > 0:
            page = total_pages

        # 计算当前页的文章范围
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        posts = all_posts[start_idx:end_idx]

        # 传递分页信息到模板
        pagination = {
            'page': page,
            'per_page': per_page,
            'total_posts': total_posts,
            'total_pages': total_pages,
            'has_prev': page > 1,
            'has_next': page < total_pages,
            'prev_page': page - 1 if page > 1 else None,
            'next_page': page + 1 if page < total_pages else None
        }

        return render_template('index.html', posts=posts, pagination=pagination, q=search_query)
    except Exception as e:
        # 控制台打印完整错误，便于排查 500
        logger.error(f"获取文章列表失败: {str(e)}", exc_info=True)
        traceback.print_exc()
        # 仍返回 200，页面显示错误信息，方便了解此错误
        return render_template('index.html', posts=[], error=str(e))


@app.route('/post/<slug>')
@cache.cached(timeout=3600, key_prefix=lambda: f'post_{request.view_args.get("slug")}')  # 缓存 1 小时
def post(slug):
    """文章详情页：从 Notion 拉取正文并渲染"""
    logger.info(f"正在获取文章: {slug}")
    post_data = get_post_content(slug)
    if post_data is None:
        logger.warning(f"文章未找到: {slug}")
        abort(404)
    logger.info(f"成功获取文章: {post_data.get('title', slug)}")

    # 获取相关文章推荐
    related = get_related_posts(
        current_slug=slug,
        tags=post_data.get('tags', []),
        category=post_data.get('category', ''),
        limit=3
    )

    return render_template('post.html', post=post_data, related_posts=related)

@app.route('/about')
def about():
    """极简 About 页面"""
    return render_template('about.html')


@app.route('/archives')
@cache.cached(timeout=600, key_prefix='archives_page')
def archives():
    """文章归档页面 (Archives page)"""
    from collections import defaultdict
    try:
        posts = get_posts() or []
        # 按年份和月份分组
        archives_dict = defaultdict(lambda: defaultdict(list))
        for post in posts:
            date_str = post.get('date') or ''
            if date_str:
                year = date_str[:4]
                month = date_str[5:7]
                archives_dict[year][month].append(post)

        # 转换为排序列表
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

        return render_template('archives.html', archives=archives_list)
    except Exception as e:
        logger.error(f"获取归档失败: {str(e)}", exc_info=True)
        return render_template('archives.html', archives=[], error=str(e))


@app.route('/tags')
@cache.cached(timeout=600, key_prefix='tags_page')
def tags():
    """标签页面 (Tags page)"""
    from collections import Counter, defaultdict
    try:
        posts = get_posts() or []
        # 统计所有标签
        tag_counter = Counter()
        tag_posts = defaultdict(list)

        for post in posts:
            for tag in (post.get('tags') or []):
                tag_counter[tag] += 1
                tag_posts[tag].append(post)

        # 按文章数量排序
        tags_list = [
            {'name': tag, 'count': count, 'posts': tag_posts[tag]}
            for tag, count in tag_counter.most_common()
        ]

        return render_template('tags.html', tags=tags_list)
    except Exception as e:
        logger.error(f"获取标签失败: {str(e)}", exc_info=True)
        return render_template('tags.html', tags=[], error=str(e))


@app.route('/category/<name>')
@cache.cached(timeout=300, key_prefix=lambda: f'category_{request.view_args.get("name")}')
def category(name):
    """按分类显示文章列表"""
    try:
        logger.info(f"正在获取分类文章: {name}")
        posts = get_posts(category=name)
        logger.info(f"分类 {name} 获取到 {len(posts)} 篇文章")
        return render_template('index.html', posts=posts)
    except Exception as e:
        logger.error(f"获取分类 {name} 失败: {str(e)}", exc_info=True)
        traceback.print_exc()
        return render_template('index.html', posts=[], error=str(e))


@app.errorhandler(404)
def page_not_found(e):
    """自定义 404 页面"""
    return render_template('404.html'), 404


@app.route('/sitemap.xml', methods=['GET'])
def sitemap():
    """动态生成 sitemap.xml"""
    posts = []
    try:
        posts = get_posts() or []
    except Exception:
        posts = []

    # build XML
    host_index = url_for('index', _external=True)
    host_about = url_for('about', _external=True)
    url_entries = []

    def fmt_date(d):
        if not d:
            return ''
        return (d[:10] if isinstance(d, str) else str(d))

    # Home
    url_entries.append({
        'loc': host_index,
        'lastmod': '',
        'changefreq': 'daily',
        'priority': '1.0'
    })
    # About
    url_entries.append({
        'loc': host_about,
        'lastmod': '',
        'changefreq': 'monthly',
        'priority': '0.5'
    })
    # Posts
    for p in posts:
        slug = p.get('slug') or ''
        if not slug:
            continue
        loc = url_for('post', slug=slug, _external=True)
        lastmod = fmt_date(p.get('date'))
        url_entries.append({
            'loc': loc,
            'lastmod': lastmod,
            'changefreq': 'weekly',
            'priority': '0.8'
        })

    xml_parts = ['<?xml version="1.0" encoding="UTF-8"?>',
                 '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for u in url_entries:
        xml_parts.append('  <url>')
        xml_parts.append(f'    <loc>{u["loc"]}</loc>')
        if u.get('lastmod'):
            xml_parts.append(f'    <lastmod>{u["lastmod"]}</lastmod>')
        xml_parts.append(f'    <changefreq>{u["changefreq"]}</changefreq>')
        xml_parts.append(f'    <priority>{u["priority"]}</priority>')
        xml_parts.append('  </url>')
    xml_parts.append('</urlset>')
    xml = '\n'.join(xml_parts)
    response = make_response(xml)
    response.headers['Content-Type'] = 'application/xml'
    return response


@app.route('/robots.txt')
def robots():
    """动态生成 robots.txt"""
    sitemap_url = url_for('sitemap', _external=True)
    lines = [
        "User-agent: *",
        "Disallow:",
        "",
        f"Sitemap: {sitemap_url}"
    ]
    text = "\n".join(lines)
    resp = make_response(text)
    resp.headers['Content-Type'] = 'text/plain'
    return resp


@app.route('/feed.xml')
@app.route('/rss.xml')
@app.route('/atom.xml')
def rss_feed():
    """动态生成 RSS Feed (RSS Feed generation)"""
    from datetime import datetime
    import html as html_module

    posts = []
    try:
        posts = get_posts() or []
    except Exception:
        posts = []

    # 只包含前 20 篇文章
    posts = posts[:20]

    # 构建 RSS XML
    site_url = url_for('index', _external=True).rstrip('/')
    site_title = "Neobee's Blog"
    site_description = "Hack The Box Writeups & Cybersecurity Methodology"

    def format_rfc822(date_str):
        """将 ISO 日期转换为 RFC 822 格式"""
        if not date_str:
            return datetime.now().strftime('%a, %d %b %Y %H:%M:%S +0000')
        try:
            dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            return dt.strftime('%a, %d %b %Y %H:%M:%S +0000')
        except Exception:
            return datetime.now().strftime('%a, %d %b %Y %H:%M:%S +0000')

    xml_parts = ['<?xml version="1.0" encoding="UTF-8"?>']
    xml_parts.append('<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">')
    xml_parts.append('  <channel>')
    xml_parts.append(f'    <title>{html_module.escape(site_title)}</title>')
    xml_parts.append(f'    <link>{site_url}</link>')
    xml_parts.append(f'    <description>{html_module.escape(site_description)}</description>')
    xml_parts.append(f'    <language>zh-CN</language>')
    xml_parts.append(f'    <lastBuildDate>{format_rfc822(posts[0].get("date") if posts else None)}</lastBuildDate>')
    xml_parts.append(f'    <atom:link href="{site_url}/feed.xml" rel="self" type="application/rss+xml" />')

    for post in posts:
        slug = post.get('slug') or ''
        if not slug:
            continue

        title = post.get('title') or '无标题'
        link = url_for('post', slug=slug, _external=True)
        description = post.get('summary') or ''
        pub_date = format_rfc822(post.get('date'))
        category = post.get('category') or ''

        xml_parts.append('    <item>')
        xml_parts.append(f'      <title>{html_module.escape(title)}</title>')
        xml_parts.append(f'      <link>{link}</link>')
        xml_parts.append(f'      <guid isPermaLink="true">{link}</guid>')
        xml_parts.append(f'      <description>{html_module.escape(description)}</description>')
        xml_parts.append(f'      <pubDate>{pub_date}</pubDate>')
        if category:
            xml_parts.append(f'      <category>{html_module.escape(category)}</category>')

        # 添加标签
        for tag in (post.get('tags') or []):
            xml_parts.append(f'      <category>{html_module.escape(tag)}</category>')

        xml_parts.append('    </item>')

    xml_parts.append('  </channel>')
    xml_parts.append('</rss>')

    xml = '\n'.join(xml_parts)
    response = make_response(xml)
    response.headers['Content-Type'] = 'application/rss+xml; charset=utf-8'
    return response


@app.route('/api/translate/<slug>', methods=['POST'])
@csrf_exempt  # API 端点，禁用 CSRF 保护
@limiter.limit("10 per hour")
def translate_post(slug):
    """
    AI 翻译 API (AI Translation API)
    使用 LLM 翻译文章内容，保留代码块语法，仅翻译注释
    """
    import traceback
    from flask import jsonify

    try:
        # ========== 第一道防线：环境变量检查 ==========
        logger.info(f"[翻译请求] 收到翻译请求: {slug}")

        # 检查 API Key 是否配置
        if not Config.LLM_API_KEY:
            logger.error("[配置错误] LLM_API_KEY 环境变量未设置")
            logger.error(f"[配置信息] LLM_BASE_URL: {Config.LLM_BASE_URL}")
            logger.error(f"[配置信息] LLM_MODEL: {Config.LLM_MODEL}")
            return jsonify({
                'success': False,
                'error': 'Server Configuration Error: API Key missing in production environment.'
            }), 500

        logger.info(f"[配置检查] API Key 已配置: {Config.LLM_API_KEY[:20]}...")
        logger.info(f"[配置检查] Base URL: {Config.LLM_BASE_URL}")
        logger.info(f"[配置检查] Model: {Config.LLM_MODEL}")

        # ========== 第二道防线：缓存检查 ==========
        cache_key = f'translated_{slug}'
        cached_translation = cache.get(cache_key)
        if cached_translation:
            logger.info(f"[缓存命中] 返回缓存的翻译: {slug}")
            return jsonify({
                'success': True,
                'content_html': cached_translation,
                'from_cache': True
            }), 200

        # ========== 第三道防线：获取文章内容 ==========
        logger.info(f"[开始翻译] 正在获取文章内容: {slug}")
        try:
            post_data = get_post_content(slug)
        except Exception as e:
            logger.error(f"[获取文章失败] {str(e)}")
            traceback.print_exc()
            return jsonify({
                'success': False,
                'error': f'获取文章内容失败: {str(e)}'
            }), 500

        if not post_data:
            logger.warning(f"[文章不存在] 文章未找到: {slug}")
            return jsonify({
                'success': False,
                'error': '文章未找到'
            }), 404

        original_html = post_data.get('content_html', '')
        if not original_html:
            logger.warning(f"[内容为空] 文章内容为空: {slug}")
            return jsonify({
                'success': False,
                'error': '文章内容为空，无法翻译'
            }), 400

        logger.info(f"[内容长度] 原文长度: {len(original_html)} 字符")

        # ========== 第四道防线：检查依赖库 ==========
        try:
            from openai import OpenAI
            logger.info("[依赖检查] OpenAI 库已加载")
        except ImportError as import_err:
            logger.error(f"[依赖缺失] OpenAI 库未安装: {str(import_err)}")
            traceback.print_exc()
            return jsonify({
                'success': False,
                'error': 'OpenAI 库未安装，请运行 pip install openai'
            }), 500

        # ========== 第五道防线：初始化客户端 ==========
        try:
            logger.info("[客户端初始化] 正在创建 OpenAI 客户端...")
            client = OpenAI(
                api_key=Config.LLM_API_KEY,
                base_url=Config.LLM_BASE_URL
            )
            logger.info("[客户端初始化] OpenAI 客户端创建成功")
        except Exception as client_err:
            logger.error(f"[客户端初始化失败] {str(client_err)}")
            traceback.print_exc()
            return jsonify({
                'success': False,
                'error': f'初始化翻译客户端失败: {str(client_err)}'
            }), 500

        # ========== 第六道防线：调用 LLM 翻译 ==========
        system_prompt = """You are an expert technical translator. Translate the provided HTML content from Chinese to English (or vice versa).

CRITICAL RULES:
1. For any content inside <pre><code> tags, you MUST strictly preserve the programming language syntax, function names, and variables.
2. You are ONLY allowed to translate the inline code comments (e.g., text after //, #, /* */) and explanatory string literals.
3. Do not break the HTML structure. Keep all HTML tags intact.
4. Preserve all class names, IDs, and attributes.
5. For technical terms, use industry-standard English translations.

Example:
Input: <code class="language-python"># 这是注释\nprint("你好")</code>
Output: <code class="language-python"># This is a comment\nprint("Hello")</code>"""

        try:
            logger.info(f"[LLM 调用] 开始调用模型: {Config.LLM_MODEL}")
            logger.info(f"[LLM 调用] 请求参数 - temperature: 0.3, max_tokens: 8000")

            response = client.chat.completions.create(
                model=Config.LLM_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Translate this HTML content:\n\n{original_html}"}
                ],
                temperature=0.3,
                max_tokens=8000
            )

            logger.info("[LLM 调用] API 调用成功")

            translated_html = response.choices[0].message.content
            logger.info(f"[翻译完成] 译文长度: {len(translated_html)} 字符")

            # 存入缓存（缓存 1 小时）
            cache.set(cache_key, translated_html, timeout=3600)
            logger.info(f"[缓存写入] 翻译结果已缓存: {slug}")

            return jsonify({
                'success': True,
                'content_html': translated_html,
                'from_cache': False
            }), 200

        except Exception as llm_err:
            logger.error(f"[LLM 调用失败] {str(llm_err)}")
            logger.error(f"[错误类型] {type(llm_err).__name__}")
            traceback.print_exc()

            # 尝试提取更详细的错误信息
            error_detail = str(llm_err)
            if hasattr(llm_err, 'response'):
                logger.error(f"[API 响应] {llm_err.response}")
            if hasattr(llm_err, 'status_code'):
                logger.error(f"[HTTP 状态码] {llm_err.status_code}")

            return jsonify({
                'success': False,
                'error': f'翻译服务调用失败: {error_detail}'
            }), 500

    except Exception as e:
        # ========== 最外层异常捕获 ==========
        logger.error(f"[未知错误] 翻译 API 发生未预期的错误: {str(e)}")
        logger.error(f"[错误类型] {type(e).__name__}")
        traceback.print_exc()

        return jsonify({
            'success': False,
            'error': f'服务器内部错误: {str(e)}'
        }), 500


if __name__ == '__main__':
    # 获取 Railway 分配的端口，如果没有则默认 5000
    port = int(os.environ.get("PORT", 5000))
    # 必须 host='0.0.0.0'
    app.run(host='0.0.0.0', port=port)
