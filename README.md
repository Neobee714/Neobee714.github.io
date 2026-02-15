# Neobee's Blog

基于 Flask + Notion API 的极简黑客风个人博客（支持 HTB 靶机与方法论文章展示）。

## 技术栈

- Python Flask (推荐 2.3.x)
- Notion API (作为 CMS) via notion-client
- 前端：Tailwind CSS + DaisyUI、FontAwesome、Prism.js（代码高亮）
- 增强：Flask-Caching (cachelib)、medium-zoom（图片点击放大）

## 项目结构（简要）

```
Blog-2/
├── app.py                 # Flask 主入口、路由与缓存
├── config.py              # 配置与环境变量校验
├── services/
│   └── notion_service.py  # 与 Notion 交互：获取列表与文章内容
├── templates/             # Jinja2 模板（index, post, about, 404 等）
├── static/                # 静态资源（avatar, css, js, images）
├── requirements.txt       # Python 依赖
├── Dockerfile
└── README.md
```

## 必要环境变量（.env）

在项目根创建 `.env`，至少配置：

- NOTION_TOKEN: Notion 集成的 API token  
- NOTION_DATABASE_ID: Notion 数据库 ID  
- SECRET_KEY: Flask secret（可选）  
- GISCUS_REPO / GISCUS_REPO_ID / GISCUS_CATEGORY / GISCUS_CATEGORY_ID（可选，用于评论）

注意：Notion 数据库中使用的列名为中文（示例）：`机器名称`/`Slug`/`日期`/`类型`/`简介`/`标签` 等，服务端代码已做空值安全读取。

## 安装与本地运行

建议在虚拟环境中运行（Windows 示例）：

```powershell
python -m venv .venv
.venv\Scripts\activate   # 若受限可使用 activate.bat
pip install -r requirements.txt
cp .env.example .env    # 或手动创建 .env 并填写变量
python app.py
```

生产建议使用 gunicorn：

```bash
gunicorn app:app --bind 0.0.0.0:$PORT
```

或使用 Render / Railway 等 PaaS 直接从 GitHub 部署（Build: pip install -r requirements.txt；Start: gunicorn app:app）。

## 主要功能亮点

- 支持两类文章样式：HTB（靶机）和 Methodology（方法论），在首页以左右分栏卡片显示（左侧内容、右侧详情侧边栏）。  
- 安全解析 Notion properties（支持中文列名、空值容错）。  
- 页面性能：支持 Skeleton Loader（骨架屏）、前端实时搜索（按标题/标签）、图片点击放大（medium-zoom）。  
- 代码体验：Prism.js 代码高亮；已强制代码块自动换行以避免水平滚动。  
- 缓存：集成 Flask-Caching（SimpleCache / FileSystemCache，建议生产使用 Redis），减少 Notion API 调用频率。

## 注意与约定

- 本仓库的模板里使用了中文列名（`类型`、`简介`、`标签` 等），请确保 Notion 数据库列名一致或相应调整服务端代码。  
- requirements.txt 已列出推荐依赖，若遇依赖冲突请先在干净虚拟环境中安装。  
- 若计划部署到 Vercel，请注意 Vercel 更适合 Serverless 或前端，推荐后端使用 Render/Railway（长期进程支持）。

## 常见命令

- 本地运行： `python app.py`  
- 生产（gunicorn）： `gunicorn app:app --bind 0.0.0.0:$PORT`  
- 安装依赖： `pip install -r requirements.txt`

如需，我可以：
- 帮你把仓库初始化并推到 GitHub；  
- 为 Render 写好部署配置（Start command、环境变量说明）；  
- 或把后端改成 serverless 以便部署到 Vercel（需要重构）。  
