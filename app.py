"""
Neobee's Blog - Flask 主入口文件
"""
import os
import traceback
from flask import Flask, render_template, abort, make_response, url_for, render_template_string
from config import Config
from services.notion_service import get_posts, get_post_content, get_categories
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
        cats = get_categories() or []
    except Exception:
        cats = []
    return {'categories': cats}



@app.route('/')
@cache.cached()
def index():
    """首页路由：渲染文章列表"""
    try:
        posts = get_posts()
        return render_template('index.html', posts=posts)
    except Exception as e:
        # 控制台打印完整错误，便于排查 500
        traceback.print_exc()
        # 仍返回 200，页面显示错误信息，方便了解此错误
        return render_template('index.html', posts=[], error=str(e))


@app.route('/post/<slug>')
@cache.cached()
def post(slug):
    """文章详情页：从 Notion 拉取正文并渲染"""
    post_data = get_post_content(slug)
    if post_data is None:
        abort(404)
    return render_template('post.html', post=post_data)

@app.route('/about')
def about():
    """极简 About 页面"""
    return render_template('about.html')


@app.route('/category/<name>')
def category(name):
    """按分类显示文章列表"""
    try:
        posts = get_posts(category=name)
        return render_template('index.html', posts=posts)
    except Exception as e:
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


if __name__ == '__main__':
    # 获取 Railway 分配的端口，如果没有则默认 5000
    port = int(os.environ.get("PORT", 5000))
    # 必须 host='0.0.0.0'
    app.run(host='0.0.0.0', port=port)
