# 需求文档：Obsidian → Blog 迁移（告别 Notion）

## 1. 背景与目标

### 1.1 背景

当前博客基于 Flask + Notion API，靠 `sync_notion.py` 把 Notion 数据库同步到本地 JSON，再由 Flask 渲染。痛点：
- Notion 作为 CMS 体验割裂，写作要在 Obsidian 里才舒服
- 页面显示内容和本地 Obsidian 笔记不一致，要双向搬运
- Notion API 有速率限制、临时链接失效等问题

### 1.2 目标

把**写作源**切换到 Obsidian（GitHub 私有仓库托管），博客自动从仓库构建并部署。
一次写作，多处产出：本地用 Obsidian，发布用 blog。

### 1.3 范围外（Non-Goals）

- 不保留 Notion 作为后备数据源（彻底替换）
- 不做评论系统重构（沿用 Giscus 或暂缓）
- 不做后台管理 UI（Obsidian 本身就是后台）

---

## 2. 已敲定的技术决策

| # | 决策 | 选定 |
|---|---|---|
| A | 架构形态 | **纯 SSG** |
| B | 框架 | **Astro** |
| C | 仓库组织 | **双仓库**：① Obsidian Vault = **私有仓库**（只存笔记 + 图片）；② 博客站点代码 = **公开仓库**（Astro 项目、翻译脚本、CI 配置）。Cloudflare Pages 绑公仓；Actions 在公仓里跑，通过 SSH deploy key 拉取私仓内容 |
| D | 部署平台 | **自建 VPS（`45.63.124.218`）+ Docker Compose**；保留 Cloudflare 作为 DNS（不启用橙云代理，Proxy status=DNS only）；Astro 产物通过 GitHub Actions `rsync` 到 VPS，由一个极简 Nginx 容器吐静态文件；外层复用现有的 `neobee-nginx` 反代 + Let's Encrypt 证书 |
| E | 发布范围 | **所有类型**只要 frontmatter 里有 `发布: true` 就发布（不区分目录 / 类型） |
| F | 品牌名 | **Xyvora**（替换原 "Neobee's Blog"） |
| G | 访问统计 | **Cloudflare Web Analytics**（站点级 PV/UV，无需每篇显示徽章；即使 DNS 不开橙云代理，Web Analytics 仍可通过站点内嵌 script 正常工作） |
| H | 评论 | **保留 Giscus**（与 GitHub Discussions 打通，静态架构天然兼容） |
| I | 双语 | **中文先行**：前端预留中英切换按钮；**翻译作为自动化流水线的一环**（push → CI 拉取 → LLM 翻译 → 翻译产物存仓库 → 构建 → 部署）；已翻译的文章复用缓存，不重复翻译 |

---

## 3. 用户故事与功能需求（EARS 格式）

### 3.1 核心工作流

**US-01：写作与发布**
> 作为博主，我想在 Obsidian 里写笔记并 `git push`，希望博客在几分钟内自动更新。

- REQ-01-1 系统**应**扫描 GitHub 仓库内所有 `.md` 文件作为候选
- REQ-01-2 系统**应**仅发布 frontmatter 中满足 `发布: true` 的文章
- REQ-01-3 当 frontmatter 缺少 `发布` 字段，系统**应**默认视为不发布
- REQ-01-4 系统**应**在 `git push` 后 **≤ 5 分钟**内完成重新构建与部署
- REQ-01-5 系统**应**记录构建日志（成功/失败条目数、跳过原因）到 Actions 输出

### 3.2 锁住文章的可见性

**US-02：占位但保密**
> 作为博主，有些 HTB 靶机还没退役，我想让它出现在列表里（证明我已做完），但点进去只显示"暂未公开"。

- REQ-02-1 当 `是否锁住: Yes` 时，文章**应**出现在列表、分类、标签、RSS、sitemap 中
- REQ-02-2 当 `是否锁住: Yes` 时，文章详情页**应**隐藏正文，显示统一的"ACCESS DENIED / 暂未公开"占位区块（复用原 `post.html` 的 ACCESS DENIED 样式，视觉风格为终端报错）
- REQ-02-3 当 `是否锁住: Yes` 时，文章的 `summary` / `tags` / `category` / `date` / `cover` 等元数据**应**正常显示（便于 SEO 与列表卡片展示）
- REQ-02-4 值 `Yes` / `是` / `true` / `locked` 均**应**视为锁住（大小写不敏感）
- REQ-02-5 值缺失 / `No` / `否` / `false` **应**视为未锁住

### 3.3 URL 与向后兼容

**US-03：链接永久有效**
> 作为博主，我之前分享过 `https://neobee.top/post/htb-bruno` 这样的链接，要保证迁移后依然能打开。

- REQ-03-1 文章 URL **应**为 `https://neobee.top/post/<Slug>/`（尾斜杠可由平台决定，但不允许 404）
- REQ-03-2 `<Slug>` **应**从 frontmatter 的 `Slug` 字段获取
- REQ-03-3 当 `Slug` 缺失时，系统**应**跳过该文章并在构建日志中警告（不自动生成 slug，避免链接变化）
- REQ-03-4 同一 Slug 不允许在两篇文章中出现，构建**应**失败并报错
- REQ-03-5 系统**应**保留以下路由：
  - `/` 首页
  - `/post/<slug>/` 文章页
  - `/category/<name>/` 分类页
  - `/tags/` 标签索引页
  - `/archives/` 按年月归档页
  - `/about/` 关于页
  - `/sitemap.xml` / `/robots.txt` / `/feed.xml` (RSS)

### 3.4 Frontmatter 字段映射

**US-04：字段一致**
> 作为博主，我在 Obsidian 里写的元数据要和博客卡片、详情页展示的一致。

- REQ-04-1 系统**应**识别以下 frontmatter 字段并映射到内部数据模型：

| Obsidian 字段 | 内部字段 | 类型 | 必需 | 说明 |
|---|---|---|---|---|
| `Slug` | `slug` | string | ✅ | URL 片段，全站唯一 |
| `发布` | `published` | boolean | ✅ | 必须为 `true` 才发布 |
| `是否锁住` | `locked` | boolean | - | 默认 `false` |
| `日期` | `date` | string (ISO) | ✅ | 支持中文格式转换，见 REQ-04-2 |
| `类型` | `category` | string | - | 如 HTB / 方法论 / 工具 |
| `难度` | `difficulty` | string | - | 仅 HTB 类显示 |
| `操作系统` | `os` | string | - | 仅 HTB 类显示 |
| `tags` | `tags` | string[] | - | 支持 `tag1, tag2` 或 YAML list |
| `简介` | `summary` | string | - | 列表卡片摘要 |
| `状态` | `status` | string | - | 目前用于过滤，见 REQ-04-3 |

- REQ-04-2 日期字段**应**支持以下格式解析为 ISO 8601（`YYYY-MM-DD`）：
  - `2026-01-03`（ISO，直接使用）
  - `2026年1月3日`（中文，解析为 `2026-01-03`）
  - `2026/1/3`（斜杠，解析为 `2026-01-03`）
  - 无法解析时**应**使用文件 `mtime` 并在日志中警告

- REQ-04-3 `状态` 字段语义（以 HTB 模板为准）：
  - `已完成` / `complete` → 可发布（配合 `发布: true`）
  - `进行中` / `draft` → 不发布（即使 `发布: true`）
  - `已锁住` → 等同 `是否锁住: Yes`（向后兼容当前 Notion 语义）

### 3.5 Markdown 渲染扩展

**US-05：Obsidian 独有语法能正确渲染**
> 作为博主，我在笔记里用了 `![[image.png]]`、`[[other note]]`、`> [!warning]` 这些 Obsidian 语法，发布后要正常显示。

- REQ-05-1 系统**应**将 `![[图片.png]]` 转换为 `<img src="/images/图片.png">`（图片路径见 REQ-06-1）
- REQ-05-2 系统**应**将 `![[image.png|300]]` 渲染为 `<img width="300">`，`|300x200` 渲染为 `width + height`
- REQ-05-3 系统**应**将 `[[note-name]]` 转换为 `<a href="/post/<slug>">note-name</a>`：
  - 若目标笔记已发布：正常链接
  - 若目标笔记存在但未发布：渲染为 `<span class="broken-link">note-name</span>` 加 title 提示
  - 若目标笔记不存在：同上并在构建日志警告
- REQ-05-4 系统**应**将 `[[note-name|别名]]` 的显示文本替换为"别名"
- REQ-05-5 系统**应**将 `[[note#标题]]` 渲染为带 `#heading-anchor` 的链接
- REQ-05-6 系统**应**将 Obsidian Callout 转换为对应样式的 `<aside>` 块：
  - `> [!note]` / `> [!tip]` / `> [!warning]` / `> [!danger]` / `> [!info]` / `> [!success]` / `> [!question]` / `> [!failure]` / `> [!bug]` / `> [!example]` / `> [!quote]` / `> [!abstract]`
  - 支持 `[!note]-`（默认折叠）和 `[!tip]+`（默认展开），渲染为 `<details>`
- REQ-05-7 系统**应**支持标准 GFM：表格、任务列表、删除线、脚注、代码块
- REQ-05-8 系统**应**对代码块应用语法高亮（保留现 Prism.js 能力或用 Shiki）
- REQ-05-9 系统**应**渲染 LaTeX 数学公式（行内 `$...$`、块级 `$$...$$`），使用 KaTeX
- REQ-05-10 系统**应**渲染 Mermaid 图表
- REQ-05-11 系统**应**保留 Obsidian 的 `==高亮==` 语法，渲染为 `<mark>`
- REQ-05-12 系统**应**忽略 Obsidian 的注释语法 `%% ... %%`（不输出到 HTML）
- REQ-05-13 系统**应**忽略 Dataview / Templater 代码块（`dataview` / 以 `<%*` 开头的块），不渲染

### 3.6 资源（图片）处理

**US-06：图片不丢失**
> 作为博主，笔记里的 `![[image 1.png]]` 引用的是 `SecNotes/assets/` 里的文件，发布后要能正常显示。

- REQ-06-1 系统**应**在构建时遍历 vault 中所有 `assets/` 目录，把引用到的图片**拷贝**到站点 `public/images/` 下
- REQ-06-2 系统**应**在构建拷贝图片时，将原文件名中的空格、中文字符规范化为 ASCII 安全形式（空格 → `-`，中文 → 拼音或 hash），并同步改写 Markdown 引用里的文件名（原 vault 文件不动，只影响 `public/images/` 产物和最终 HTML）
- REQ-06-3 系统**应**对图片添加 `loading="lazy"`
- REQ-06-4 系统**应**跳过未被引用的图片（不拷贝，节省带宽）
- REQ-06-5 系统**应**支持外链图片 `![alt](https://...)` 原样保留（不下载镜像）
- REQ-06-6 图片路径解析顺序：
  1. 优先在笔记同目录匹配
  2. 其次在 `SecNotes/assets/` 匹配
  3. 再其次在整个 vault 的任意 `assets/` 子目录匹配
  4. 都找不到：渲染为 `<span class="missing-image">⚠ Missing: xxx.png</span>`，构建日志警告

### 3.7 前端视觉

**US-07：高端美观**
> 作为博主，我希望博客视觉接近 `premium_blog_frontend.jsx` 的参考设计。

- REQ-07-1 前端**应**支持深色 / 浅色主题切换，持久化到 `localStorage`
- REQ-07-2 列表页**应**采用卡片网格布局（3 列 @ lg，2 列 @ md，1 列 @ sm）
- REQ-07-3 无封面图时系统**应**生成 **AI Cover 占位图**（渐变 + 网格 + 文章标题 + 标签色），色板按 `category` 映射：
  - HTB → emerald（绿）
  - 方法论 → sky（蓝）
  - 工具 → violet（紫）
  - CTF → rose（粉）
  - 其他 → zinc（灰）
- REQ-07-4 文章页**应**包含：
  - 阅读进度条（顶部细条，随滚动增长）
  - 目录（TOC，h1~h3，点击跳转 + 当前位置高亮）
  - 顶部元信息（日期 / 阅读时长 / 分类 / 标签）
  - 底部分享 + 评论（Giscus 保留）
  - 返回顶部按钮
- REQ-07-5 首页**应**包含：
  - Hero 区域（标题 + 简介 + 终端风格装饰）
  - 全局搜索按钮（Ctrl+K / ⌘+K 唤起，支持搜标题 / 标签 / 分类 / 摘要）
  - 分类快筛
  - 精选文章（最新一篇）+ 最新文章网格
- REQ-07-6 系统**应**复用原 `premium_blog_frontend.jsx` 中的 AI Cover / 卡片悬停 / 标签胶囊样式
- REQ-07-7 字体**应**使用：
  - 正文 `Inter` / system-ui
  - 代码 `JetBrains Mono`
- REQ-07-8 对卡片、按钮**应**应用 Framer Motion 轻量动效（入场 stagger、hover 位移）
- REQ-07-9 站点品牌名**应**为 **Xyvora**（顶部导航、页面 `<title>`、RSS 频道名、sitemap host 描述、schema.org `publisher.name` 全部统一使用）

### 3.8 SEO 与社交

**US-08：搜索引擎友好**

- REQ-08-1 每个页面**应**输出 `<title>` / `<meta description>` / `<meta keywords>`
- REQ-08-2 每个文章页**应**输出 Open Graph 标签（`og:title` / `og:description` / `og:image` / `og:type=article`）
- REQ-08-3 每个文章页**应**输出 Twitter Card（`summary_large_image`）
- REQ-08-4 每个文章页**应**输出 schema.org `BlogPosting` JSON-LD
- REQ-08-5 系统**应**生成 `/sitemap.xml`，包含所有发布文章（含锁住的）
- REQ-08-6 系统**应**生成 `/robots.txt` 允许全站抓取（锁住文章不阻止抓取，因为正文已经是占位区）
- REQ-08-7 系统**应**生成 `/feed.xml`（RSS 2.0）包含最近 20 篇
- REQ-08-8 每个页面**应**输出 `<link rel="canonical">`
- REQ-08-9 无封面图时 `og:image` **应**使用 AI Cover 的 PNG 版本（构建时生成），避免社交分享空白
- REQ-08-10 站点**应**在 `<head>` 中支持输出**搜索引擎验证 meta 标签**，值来自构建时环境变量（未配置则不输出）：
  - `GOOGLE_SITE_VERIFICATION` → `<meta name="google-site-verification" content="...">`
  - `BING_SITE_VERIFICATION` → `<meta name="msvalidate.01" content="...">`
  - `BAIDU_SITE_VERIFICATION` → `<meta name="baidu-site-verification" content="...">`（可选，未来扩展）
- REQ-08-11 `robots.txt` **应**显式包含 `Sitemap: https://<host>/sitemap.xml` 行，让 Google / Bing 的爬虫能自动发现站点地图
- REQ-08-12 Google Search Console 的配置**应**记录在 site-repo `README.md` 中的"部署与运维"章节，包含：
  - 首次验证域名的步骤（推荐用 HTML meta 标签方式，避免 DNS 依赖）
  - 如何在 GSC 中手动提交 `sitemap.xml` URL
  - 站点每次部署后 GSC 自动抓取的预期时效（几小时到几天）

### 3.9 自动化同步与翻译流水线

**US-09：推送即部署（含翻译）**

**仓库布局：**

```
vault-repo（私有）              site-repo（公开）
├── SecNotes/                   ├── src/                   ← Astro 页面/布局/组件
│   ├── 40-Archive/...          ├── public/                ← 站点静态资源
│   ├── assets/                 ├── scripts/
│   └── ...                     │   └── translate.py       ← LLM 翻译脚本
├── Templates/                  ├── astro.config.mjs
└── README.md                   ├── package.json
                                ├── .github/workflows/
                                │   └── build.yml          ← 触发、翻译、构建、部署
                                └── README.md
```

**工作流（VPS 部署版）：**

```
① vault-repo push (main)
  ↓
② vault-repo 的 .github/workflows/notify.yml 发 repository_dispatch 到 site-repo
  ↓
③ site-repo 的 build.yml 触发：
    a. checkout site-repo
    b. 用 SSH deploy key clone vault-repo 到 ./vault/（仅 workflow 运行期间存在）
    c. 运行 scripts/translate.py（读 vault/，写 .en.md 回 vault/）
    d. 若有新翻译 → 用 PAT push 回 vault-repo
    e. Astro 构建（读 vault/ 下笔记 + 图片，产出 dist/）
    f. 用 CI 专用 SSH key rsync dist/ → VPS 的 /root/neobee-stack/Neobee714.github.io/dist/
    g. SSH 到 VPS 执行 `docker compose up -d neobee-blog`（容器挂载 dist 为静态根目录，重启后生效）
```

- REQ-09-1 当 **vault-repo push 到 main** 时，其 workflow **应**向 site-repo 发 `repository_dispatch` 事件（event_type 如 `vault-updated`）
- REQ-09-2 当 **site-repo 收到 dispatch 事件** 或 **site-repo 自身 push** 时，`build.yml` **应**执行完整流水线（checkout site → clone vault → translate → build → rsync → docker reload）
- REQ-09-3 `build.yml` **应**支持 `workflow_dispatch` 手动触发，并支持传入参数：
  - `force_translate`：忽略翻译缓存强制全量翻译
  - `skip_translate`：跳过翻译步骤（只构建部署）
- REQ-09-4 vault-repo 的读取**应**使用 SSH deploy key（在 vault-repo Settings 添加**只读** deploy key，对应私钥放 site-repo Secrets 为 `VAULT_SSH_KEY`）
- REQ-09-5 翻译产物 commit 回 vault-repo 时**应**使用具有 vault-repo 写权限的 PAT（放 site-repo Secrets 为 `VAULT_PUSH_TOKEN`），commit 消息格式固定为 `chore(translate): update N files`，以机器账户署名以免干扰人类 commit 历史
- REQ-09-6 VPS 部署**应**使用独立签发的 ed25519 SSH key（不复用用户本地日常 SSH key），私钥放 site-repo Secrets 为 `VPS_SSH_KEY`，公钥追加到 VPS 的 `~/.ssh/authorized_keys`
- REQ-09-7 构建或部署失败时**应**不影响线上版本（`rsync` 使用原子切换或先写临时目录再 move，确保不会出现半量文件；详见 design.md §8.1）
- REQ-09-8 Actions 日志**应**打印每一阶段统计：
  - Clone 阶段：vault commit SHA / 文件数
  - 扫描阶段：总笔记数 / 已发布数 / 锁住数 / 跳过数（及跳过原因）
  - 翻译阶段：新增翻译数 / 缓存命中数 / 失败数 / 调用 token 数
  - 构建阶段：生成页面数 / 图片拷贝数 / 构建耗时 / dist 体积
  - 部署阶段：rsync 传输字节数 / Docker 容器重载耗时
- REQ-09-9 整条流水线**应**在 ≤ 5 分钟内完成（规模：< 200 篇笔记、< 500 张图片、单次 push < 10 篇文章触发翻译）

### 3.10 LLM 翻译脚本（自动化流水线中的一环）

**US-10：中文写一次，英文自动出**

- REQ-10-1 翻译脚本**应**作为 site-repo 的独立 Python 脚本（`scripts/translate.py`），不依赖 Astro、可单独运行
- REQ-10-2 翻译脚本**应**接受 `--vault <path>` 参数指向 vault 根目录（CI 里传 `./vault`，本地调试可直接指向 `F:\Work\Obsidian`）
- REQ-10-3 翻译脚本**应**仅处理 frontmatter 满足 `发布: true` 且未被锁住的文章
- REQ-10-4 翻译产物命名**应**为原文同目录、同主名 + `.en.md`：
  - 原文：`SecNotes/40-Archive/HTB Machines/htb bruno.md`
  - 译文：`SecNotes/40-Archive/HTB Machines/htb bruno.en.md`
  - 译文**写回 vault-repo**（不是 site-repo）
- REQ-10-5 翻译脚本**应**对每篇原文计算 SHA-256 哈希（frontmatter + body），写入 `.en.md` 的 frontmatter `source_hash` 字段
- REQ-10-6 当原文哈希 **未变化** 时**应**跳过（缓存命中）
- REQ-10-7 当原文哈希 **发生变化** 或 `.en.md` 不存在时**应**调用 LLM 重新翻译
- REQ-10-8 翻译内容**应**包括：标题、简介、分类名、正文（保留 Markdown 结构）
- REQ-10-9 翻译**应**保持以下元素**原样不翻**：
  - 代码块内的代码（函数名 / 变量 / 关键字）；仅代码内注释可翻
  - 命令行 / URL / 文件路径 / CVE 编号 / 工具名（nmap / BurpSuite / Metasploit 等）
  - `![[image.png]]` / `[[wiki-link]]` 等 Obsidian 语法
  - 行内代码 `` `code` ``
- REQ-10-10 翻译产物 frontmatter **应**复制原文除 `标签` 外的所有字段（日期、Slug、难度、操作系统、类型、发布、是否锁住），并追加：
  - `lang: en`
  - `source: <原文件相对路径>`
  - `source_hash: <sha256>`
  - `translated_at: <ISO timestamp>`
- REQ-10-11 翻译失败时**应**保留旧的 `.en.md`，不覆盖（避免部分翻译污染），并在日志中报告失败文件
- REQ-10-12 翻译脚本**应**支持 CLI 参数：
  - `--force`：忽略哈希强制全量翻译
  - `--only <slug>`：只翻译指定 slug 的文章
  - `--dry-run`：只报告会翻译哪些文件，不实际调用 LLM
- REQ-10-13 翻译脚本在 CI 中**应**使用 site-repo Secrets 中的 `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL`
- REQ-10-14 长文本**应**按 `<h1>` / `<h2>` 切块翻译（借鉴原 `sync_notion.py` 里的 `_split_html_by_headings` 策略），避免 token 超限

### 3.11 前端语言切换

**US-11：一键切换中英文**

- REQ-11-1 页面**应**在顶部导航显示中英切换按钮（`中 / EN`），默认语言跟随浏览器 `Accept-Language`，无匹配时默认中文
- REQ-11-2 用户选择的语言**应**持久化到 `localStorage`，跨页面生效
- REQ-11-3 每篇文章构建时**应**在**同一个 HTML 页面**内输出中英两份内容（分别包裹在 `<div class="lang-zh">` 和 `<div class="lang-en">` 中），通过 CSS 根据 `<html data-lang>` 属性切换可见性（沿用原 Flask 版本的做法）
- REQ-11-4 当对应文章的 `.en.md` 尚不存在时：
  - 英文切换按钮**应**处于 disabled 状态或显示 tooltip "EN version pending translation"
  - 强制切换到英文时**应**在文章顶部贴 banner "This post has not been translated yet"，并 fallback 到中文正文
- REQ-11-5 切换语言时 `<html lang="...">` **应**同步更新为 `zh-CN` 或 `en`（便于屏幕阅读器和搜索引擎识别）
- REQ-11-6 由于采用单页 CSS 切换，SEO 以中文版为主（`<html lang="zh-CN">`），不强制要求为英文版生成独立 URL 和 hreflang 标签（可列为未来优化项）

### 3.12 性能

- REQ-12-1 首页 LCP（Largest Contentful Paint）**应** ≤ 2.5s（Cloudflare 亚洲节点）
- REQ-12-2 文章页总 JS 体积**应** ≤ 150KB（gzipped），图片懒加载之外的首屏资源不依赖 JS 才能渲染
- REQ-12-3 所有页面**应**通过 Lighthouse Performance ≥ 90、SEO ≥ 95、Accessibility ≥ 90

### 3.13 迁移与清理

**US-13：干净切换**

- REQ-13-1 现有 `f:\Work\Program\Python\blog` 目录**应**在迁移前打 git tag（如 `legacy-flask-v1`）并 push，之后所有旧代码可归档删除
- REQ-13-2 **site-repo** 是 `Neobee714/Neobee714.github.io`（沿用现有仓库），清空旧 Flask 代码后重新填充 Astro 项目 + 翻译脚本 + CI
- REQ-13-3 **vault-repo** 是 `Neobee714/obsidian-vault`（已存在私仓），整个 `F:\Work\Obsidian` vault 推送到此
- REQ-13-4 VPS `/root/neobee-stack/docker-compose.yml` 中的 `neobee-blog` 服务**应**从"Flask + gunicorn"重构为"Nginx + 静态文件"，但**保持容器名 `neobee-blog` 不变**，以免 `neobee-nginx` 的反代配置（`proxy_pass http://neobee-blog:...`）需要改动
- REQ-13-5 VPS 现有的 `neobee-nginx` 容器、Let's Encrypt 证书、`bookkeeping-*` 相关栈**应**全部保持不动；本次迁移仅影响 `neobee-blog` 服务及其所依赖的 `neobee-redis`（redis 可移除，因为 Astro 静态站不需要缓存层）
- REQ-13-6 旧项目中的以下内容**不应**进入 site-repo 主分支：
  - `app.py` / `config.py` / `sync_notion.py` / `extract.py`
  - `services/` 整个目录（notion_service / local_data_service / analytics）
  - `templates/` / `static/` / `blog-data/`
  - `Procfile` / `start.sh` / `Dockerfile`（旧版）/ `.dockerignore`（旧版）
  - `requirements.txt`（Python 依赖整体淘汰）
- REQ-13-7 可借鉴（不直接复制）的遗产：
  - `services/notion_service.py` 里的 Callout / 代码块渲染策略 → Astro 的 remark/rehype 插件配置参考
  - `sync_notion.py` 里的 LLM 翻译分块逻辑（`_split_html_by_headings`、`execute_translation`）→ 新 `scripts/translate.py` 的起点
  - `templates/index.html` / `post.html` 的视觉结构 → Astro 组件设计参考
- REQ-13-8 所有旧技术栈依赖（`Flask*` / `gunicorn` / `notion-client` / `APScheduler` / `Flask-Caching` / `Flask-WTF` / `Flask-Limiter`）**应**不出现在 site-repo 的依赖清单中
- REQ-13-9 site-repo 的 `package.json` **应**只包含 Astro 及其生态必要依赖；`scripts/requirements.txt` **应**只包含翻译脚本必需依赖（`openai`、`python-frontmatter`、`requests`）
- REQ-13-10 VPS 上的 `/root/neobee-stack/Neobee714.github.io/` 目录**应**在切换时清理旧 Flask 源码，只保留新 Astro 构建产物 `dist/` + 新版 Dockerfile/nginx 配置

---

## 4. 验收标准（Definition of Done）

迁移完成后必须全部满足：

- [ ] 在 Obsidian 里对一篇有 `发布: true` 的笔记做修改 → push → 5 分钟内 `neobee.top/post/<slug>/` 更新
- [ ] 同一次 push 会自动触发该笔记的英文翻译（若内容有变化），翻译产物 `.en.md` commit 回源仓库
- [ ] 重复 push 同一篇（内容未改）时不再重复调用 LLM（翻译缓存命中）
- [ ] 一篇 `是否锁住: Yes` 的文章出现在首页列表，但详情页显示占位
- [ ] 原链接（如 `/post/htb-bruno`）照常可访问（没有 404）
- [ ] `![[image 1.png]]` / `[[htb-cicada]]` / `> [!warning]` / Mermaid / LaTeX 都能正确渲染
- [ ] 前端中英切换按钮可用；英文版未翻译的文章按钮禁用或提示
- [ ] Cloudflare Web Analytics 能看到站点 PV/UV
- [ ] Giscus 评论在文章页正常加载
- [ ] 站点品牌名统一为 **Xyvora**
- [ ] 站点 Lighthouse 分数达标（见 REQ-12-3）
- [ ] 深色 / 浅色主题切换正常
- [ ] 构建日志清晰能定位问题
- [ ] 旧 Flask / Notion 相关代码已清理（或归档到 `legacy` 分支）

---

## 5. 设计阶段待决的细节问题

需求阶段已无未决项，全部决策已固化：
- 架构 Astro，双仓库 vault-repo + site-repo
- 品牌 Xyvora，访问统计 Cloudflare Web Analytics，评论 Giscus
- 翻译产物 `<file>.en.md` 与原文同目录，写回 vault-repo
- 英文版采用**单页 CSS 切换**（SEO 以中文为主）
- 图片构建时**规范化文件名**（空格 → `-`）
- LLM **只用 OpenAI 兼容接口**（`openai` SDK + `LLM_BASE_URL`），不加 Claude / Gemini 抽象层
- 跨仓库触发使用 GitHub 原生 `repository_dispatch`

design.md 将基于这些决策展开具体实现。
