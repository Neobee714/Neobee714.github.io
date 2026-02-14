# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Flask-based personal blog using Notion as a headless CMS. Designed for displaying HTB (Hack The Box) writeups and methodology articles with a minimalist hacker aesthetic.

## Architecture

**Core Components:**
- [app.py](app.py): Flask application with routes, caching, and template context injection
- [config.py](config.py): Environment variable loading and validation
- [services/notion_service.py](services/notion_service.py): Notion API client, data fetching, and block-to-HTML rendering

**Data Flow:**
1. Notion database stores articles with Chinese property names (机器名称, Slug, 日期, 类型, 简介, 标签, etc.)
2. `notion_service.py` queries database, filters by status "已完成", and transforms properties into Python dicts
3. `NotionRenderer` class converts Notion blocks (headings, paragraphs, code, images, lists) to HTML
4. Flask routes serve rendered content with Flask-Caching (SimpleCache in dev, FileSystemCache in prod)
5. Templates use Jinja2 with Tailwind CSS + DaisyUI styling

**Key Design Patterns:**
- Null-safe property access throughout Notion API responses (handles missing/None values)
- Fallback Cache class when flask_caching unavailable (prevents import errors)
- pkgutil.get_loader shim for stripped Python builds
- Category injection via `@app.context_processor` for all templates

## Development Commands

**Setup:**
```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

**Run locally:**
```bash
python app.py
```
Runs on `0.0.0.0:5000` (or PORT env var)

**Production (gunicorn):**
```bash
gunicorn app:app --bind 0.0.0.0:$PORT
```

**Docker:**
```bash
docker build -t blog .
docker run -p 5000:5000 --env-file .env blog
```

## Environment Variables

Required in `.env`:
- `NOTION_TOKEN`: Notion integration API token
- `NOTION_DATABASE_ID`: Notion database ID

Optional:
- `SECRET_KEY`: Flask secret (defaults to dev key)
- `FLASK_DEBUG`: Set to "false" for production
- `GISCUS_REPO`, `GISCUS_REPO_ID`, `GISCUS_CATEGORY`, `GISCUS_CATEGORY_ID`: Comment system config

## Notion Database Schema

The database uses **Chinese property names**:
- 机器名称 (title): Article title
- Slug (rich_text): URL slug
- 日期 (date): Publication date
- 状态 (status): Must be "已完成" to appear
- 类型 (select): Category (HTB, Methodology, etc.)
- 简介 (rich_text): Summary/description
- 标签 (multi_select): Tags
- 操作系统 (select): OS (for HTB boxes)
- 难度 (select): Difficulty level
- user/root (checkbox): Flags obtained

When modifying Notion integration code, maintain null-safe access patterns like:
```python
((properties.get('操作系统') or {}).get('select') or {}).get('name') or ''
```

## Caching Strategy

- Dev: SimpleCache (in-memory, 300s timeout)
- Prod: FileSystemCache (flask_cache directory, 300s timeout)
- Routes cached: `/`, `/post/<slug>`, `/category/<name>`
- Categories cached: 600s timeout via `_get_cached_categories()`
- Clear cache by restarting app or deleting flask_cache directory

## Logging

The application uses Python's built-in logging module:
- Level: INFO in production, DEBUG in development
- Format: `%(asctime)s [%(levelname)s] %(name)s: %(message)s`
- Key events logged:
  - Article list queries and results count
  - Individual article fetches
  - Category queries
  - Locked article content skipping
  - Errors with full stack traces

## Performance Optimizations

- Locked articles ("已锁住" status) skip full content rendering to save API calls
- Category list is cached to avoid repeated schema queries
- Null-safe property access prevents unnecessary error handling

## Deployment

Configured for Railway/Render with:
- Dockerfile using Python 3.9-slim
- Gunicorn with 2 workers, 4 threads
- Dynamic PORT binding via $PORT env var
- Build: `pip install -r requirements.txt`
- Start: `gunicorn --bind 0.0.0.0:$PORT --workers 2 --threads 4 app:app`

## Supported Notion Block Types

`NotionRenderer` handles: heading_1/2/3, paragraph, bulleted_list_item, image, code. Unsupported blocks are silently skipped.

Code blocks use Prism.js syntax highlighting with language mapping (e.g., "plain text" → "plaintext").

# UI/UX 与设计系统规范 (Design System Rules)
1. **主题自适应 (Theme Adaptation):** 项目启用了 DaisyUI 的双主题切换（浅色 `lofi` / 深色 `business`）。**绝对不允许**在 Tailwind 类中使用固定的颜色值（如 `text-gray-500`, `bg-white`）。必须强制使用语义化变量（如 `text-base-content`, `bg-base-200`, `text-primary`）。
2. **卡片统一布局 (Unified Card Layout):** 首页所有文章卡片必须保持统一的“左内容+右侧边栏”布局（使用 `card md:card-side`）。左侧摘要必须使用 `line-clamp-2` 截断，右侧固定包含圆形封面图（`rounded-full`）和元数据。
3. **黑客主题 (Hacker Vibe):** 保持极简、专业的终端风格，注重代码块的阅读体验（长文本强制折行 `white-space: pre-wrap`）。

# AI 交互行为守则 (AI Interaction Guidelines)
1. **语言:** 请始终使用**中文**与我沟通和解释代码。
2. **专业术语全称:** 对于所有的专业名词以及代码中的专业函数，请务必附上全称（全称，Full Name/Term）。例如：提到 LFI 时，请说明 Local File Inclusion；提到 `render_template` 时，解释其模板渲染的全称含义。