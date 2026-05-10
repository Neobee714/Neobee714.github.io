# 任务清单：Xyvora 迁移

> 对应 `requirements.md` + `design.md`。按依赖顺序分阶段执行，每个任务包含：**Req 追溯**（哪条需求满足）、**Done when**（完成判定）。
>
> 进度标记：`[ ]` 待办 · `[~]` 进行中 · `[x]` 完成 · `[!]` 阻塞

---

## Phase 0：准备（人工一次性操作）

- [x] **0.1 准备 GitHub Tokens 与 Secrets（GitHub 仓库侧）**
  - Req: REQ-09-1, REQ-09-4, REQ-09-5
  - 动作：
    1. 确认 classic PAT（范围 `repo`）在手（你已完成 ✅）
    2. 在 `obsidian-vault` 仓库 Settings → Secrets → Actions 添加 `SITE_DISPATCH_TOKEN` = PAT
    3. 在 `Neobee714.github.io` 仓库 Secrets 添加：`VAULT_PUSH_TOKEN` = PAT
    4. 确认 `obsidian-vault` Settings → Deploy keys 里已有只读 deploy key（公钥）
    5. 把对应**私钥**添加到 `Neobee714.github.io` Secrets 为 `VAULT_SSH_KEY`
  - Done when：所需 Secret 在对应仓库的 Settings 里可见（值隐藏）

- [x] **0.2 准备 LLM 凭据**
  - Req: REQ-10-13
  - 动作：把 OpenAI 兼容 API 的 key / base_url / model 添加到 `Neobee714.github.io` Secrets：`LLM_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL`
  - Done when：3 条 Secret 可见

- [x] **0.3 生成 VPS 部署专用 SSH key**
  - Req: REQ-09-6
  - 动作（Windows PowerShell）：
    ```powershell
    ssh-keygen -t ed25519 -C "xyvora-ci-deploy" -f $env:USERPROFILE\.ssh\xyvora_ci_deploy -N '""'
    Get-Content $env:USERPROFILE\.ssh\xyvora_ci_deploy.pub | ssh root@45.63.124.218 "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"
    ssh -i $env:USERPROFILE\.ssh\xyvora_ci_deploy root@45.63.124.218 "echo OK && docker --version"
    ```
  - 然后把私钥（`~\.ssh\xyvora_ci_deploy` 文件内容）填到 site-repo Secret `VPS_SSH_KEY`
  - Done when：最后一条 ssh 命令输出 `OK Docker version ...`

- [x] **0.4 配置 VPS 相关 Secrets**
  - Req: REQ-09-6
  - 在 `Neobee714.github.io` Secrets 添加：
    - `VPS_HOST` = `45.63.124.218`
    - `VPS_USER` = `root`
    - `VPS_PATH` = `/root/neobee-stack/Neobee714.github.io/dist`
    - `VPS_COMPOSE_DIR` = `/root/neobee-stack`
  - Done when：4 条 Secret 可见

- [x] **0.5 归档现有 Flask 代码**
  - Req: REQ-13-1
  - 动作：
    ```bash
    cd f:\Work\Program\Python\blog
    git add -A && git commit -m "chore: final Flask/Notion snapshot"
    git tag legacy-flask-v1
    git push origin main --tags
    ```
  - Done when：GitHub 上能看到 `legacy-flask-v1` tag

- [x] **0.6 检查 vault-repo 状态**
  - Req: REQ-13-3
  - 动作：
    1. 确认 `F:\Work\Obsidian` 是 git 仓库，remote 指向 `github.com:Neobee714/obsidian-vault`
    2. 确认 `.gitignore` 包含 `.obsidian/workspace*.json`、`.trash/`
    3. 确认 main 分支最新 commit 推送了
  - Done when：`git remote -v` 输出正确，`git status` 干净

- [x] **0.7 VPS 现状备份（防呆）**
  - Req: REQ-09-7
  - 动作（SSH 到 VPS 执行）：
    ```bash
    cd /root/neobee-stack
    cp docker-compose.yml docker-compose.yml.pre-astro
    cp nginx.conf nginx.conf.pre-astro
    cd Neobee714.github.io
    tar czf /root/neobee-blog-flask-backup.tar.gz --exclude='.git' .
    ```
  - Done when：三份备份文件都在 VPS 上可见

---

## Phase 1：site-repo 骨架

- [x] **1.1 清空工作目录（保留 .git / .kiro）**
  - Req: REQ-13-1, REQ-13-5
  - 动作：Windows cmd：
    ```cmd
    for /d %i in (*) do @if /i not "%i"==".git" if /i not "%i"==".kiro" rmdir /s /q "%i"
    for %i in (*) do @del /q "%i"
    ```
    保留：`.git/`、`.kiro/`、`.gitignore`（如有）
  - Done when：`dir` 只剩 `.git` 和 `.kiro`

- [x] **1.2 初始化 Astro 项目**
  - Req: —（基础设施）
  - 动作：
    ```bash
    npm create astro@latest . -- --template minimal --typescript strict --git no --install no
    ```
    询问时：不要安装示例；不要覆盖 .kiro
  - Done when：`package.json`、`astro.config.mjs`、`src/pages/index.astro` 存在

- [x] **1.3 安装核心依赖**
  - Req: —
  - 动作：
    ```bash
    npm install
    npm install @astrojs/tailwind @astrojs/sitemap @astrojs/rss @astrojs/mdx @astrojs/react
    npm install tailwindcss @tailwindcss/typography
    npm install rehype-katex rehype-slug rehype-autolink-headings remark-math
    npm install unist-util-visit unist-util-remove
    npm install framer-motion lucide-react react react-dom
    npm install fuse.js
    npm install -D @types/react @types/react-dom
    ```
  - Done when：`npm run dev` 能启动默认页

- [x] **1.4 建立项目目录骨架**
  - Req: —
  - 动作：按 design §2 建空目录与占位文件：
    ```
    src/{content,lib,components/islands,layouts,styles}
    scripts/lib
    public
    .github/workflows
    ```
  - Done when：目录树与 design §2 一致

- [x] **1.5 配置 TypeScript 路径别名**
  - Req: —
  - 动作：在 `tsconfig.json` 里加 `"paths": { "@/*": ["./src/*"] }` 和 Astro 必需的 strict 设置
  - Done when：`import X from '@/lib/foo'` 不报错

---

## Phase 2：内容建模

- [x] **2.1 实现日期解析器**
  - Req: REQ-04-2
  - 文件：`src/lib/date-parser.ts`
  - 实现 design §3.2 的 `parseFlexDate`（ISO / `2026年1月3日` / `2026/1/3`），解析失败返回 undefined
  - Done when：单测覆盖 3 种格式 + 无效输入

- [x] **2.2 实现 Content Collection schema**
  - Req: REQ-04-1, REQ-04-3
  - 文件：`src/content/config.ts`
  - 实现 design §3.1 的 `flexBool` / `flexDate` / `normalizeTags` / `postsCollection`
  - Done when：`astro check` 无类型错误

- [x] **2.3 配置 Content Collection 数据源（读环境变量）**
  - Req: REQ-09-2
  - 文件：`src/content/config.ts`、`astro.config.mjs`
  - 让 Content Collection 指向环境变量 `ASTRO_VAULT_PATH`：
    - 本地开发：`.env` 里 `ASTRO_VAULT_PATH=F:/Work/Obsidian`（直接指你本地的 vault，不需要 clone 到 site-repo）
    - CI：workflow 里 `ASTRO_VAULT_PATH=${{ github.workspace }}/vault`（clone 到这里）
  - 实现方式：Astro 5 的 `glob()` loader + `base` 参数；如果路径不存在，给出清晰报错
  - Done when：
    - 本地：设置好 `.env` 后 `astro sync` 能扫到真实笔记
    - CI：build 能读到 clone 的 vault

- [x] **2.4 实现发布过滤管道**
  - Req: REQ-01-1, REQ-01-2, REQ-01-3, REQ-02-1, REQ-03-3, REQ-03-4
  - 文件：`src/lib/obsidian-parser.ts`
  - 实现 design §3.3 的 `getPublishedPosts`、`getPostWithTranslation`
  - Done when：
    - `getPublishedPosts()` 只返回 `发布:true` 的中文原文
    - 锁住的文章也在列表里
    - 未发布的文章不在返回值中

- [x] **2.5 实现 Slug 唯一性检查**
  - Req: REQ-03-4
  - 文件：`src/lib/integrations/slug-check.ts`
  - 实现 design §3.4 的 `slugUniquenessCheck` integration，在 `astro.config.mjs` 注册
  - Done when：构造两篇同 Slug 笔记 → `npm run build` 失败并报错

- [x] **2.6 Frontmatter 状态字段语义处理**
  - Req: REQ-04-3
  - 位置：`src/lib/obsidian-parser.ts`
  - `状态: 进行中` / `draft` 的文章被视为不发布（覆盖 `发布:true`）；`已锁住` 等同 `是否锁住:Yes`
  - Done when：测试 3 种状态值均符合预期

---

## Phase 3：Markdown 渲染管道

- [x] **3.1 `remark-dataview-strip`**
  - Req: REQ-05-12, REQ-05-13
  - 文件：`src/lib/remark-dataview-strip.ts`
  - 去除 `dataview` / `dataviewjs` fenced code；去除以 `<%*` 开头的 code；剥离 `%%...%%`
  - Done when：含这些语法的文章渲染后看不到它们

- [x] **3.2 `remark-callout`**
  - Req: REQ-05-6
  - 文件：`src/lib/remark-callout.ts`
  - 实现 design §4.3：识别 12 种 callout 类型、支持 `-`（折叠）和 `+`（展开）
  - 样式：`src/styles/callout.css` 定义每种类型的颜色 / 图标
  - Done when：`> [!warning] xxx` 渲染为带样式的 aside；`[!note]-` 渲染为 `<details>`

- [x] **3.3 `remark-wikilink`**
  - Req: REQ-05-1, REQ-05-2, REQ-05-3, REQ-05-4, REQ-05-5
  - 文件：`src/lib/remark-wikilink.ts`
  - 实现 design §4.2：`![[img]]` / `![[img|300]]` / `[[note]]` / `[[note|alias]]` / `[[note#heading]]`
  - 需预扫 vault 建立 "文件名 → slug" 映射（缓存在 `globalThis.__wikilinkMap`）
  - 死链用 `.wiki-link.broken` 样式标注
  - Done when：4 种语法都能正确渲染；破链构建日志 WARN

- [x] **3.4 `remark-mermaid`**
  - Req: REQ-05-10
  - 文件：`src/lib/remark-mermaid.ts`
  - 把 ` ```mermaid ` 代码块替换为 `<div data-mermaid>SOURCE</div>` 占位
  - Done when：mermaid 代码块输出占位，客户端 island 能接管（见 Task 4.8）

- [x] **3.5 `rehype-image-rewrite`**
  - Req: REQ-06-1, REQ-06-2, REQ-06-3, REQ-06-5, REQ-06-6
  - 文件：`src/lib/rehype-image-rewrite.ts`
  - 逻辑：
    1. 扫 vault 所有 `assets/` 建立文件名索引
    2. 遍历所有 `<img>`，查索引、规范化文件名、拷贝到 `dist/_images/`、改写 `src`
    3. 给所有 `<img>` 加 `loading="lazy"`
    4. 外链 `http(s)://` 保留不动
    5. 未命中 → `<span class="missing-image">⚠ Missing: xxx</span>` + 日志 WARN
  - 文件名规范化规则：空格/`_` → `-`；中文 → `py-<3hash>`；转小写
  - Done when：`![[image 1.png]]` → `/_images/image-1.png`；`![[图片.png]]` → `/_images/tp-a1b.png`

- [x] **3.6 注册插件到 Astro**
  - Req: 集成 §4.1
  - 文件：`astro.config.mjs`
  - 按 design §4.7 的顺序注册所有 remark / rehype 插件；配置 Shiki 双主题
  - Done when：`npm run build` 无插件错误

---

## Phase 4：UI 组件

- [x] **4.1 主题系统基础**
  - Req: REQ-07-1
  - 文件：`src/styles/theme.css`、`src/styles/global.css`、`src/components/ThemeToggle.astro`
  - 深浅色 CSS 变量（design §6.1），按钮切换并持久化
  - 在 `BaseLayout` 的 `<head>` 内联脚本里做主题初始化防闪烁（design §5.1）
  - Done when：刷新不闪白 / 手动切换持久化

- [x] **4.2 语言切换（单页 CSS）**
  - Req: REQ-11-1, REQ-11-2, REQ-11-5
  - 文件：`src/styles/global.css`、`src/components/LangToggle.astro`
  - design §6.2 的 CSS 规则 + 按钮脚本；默认语言跟随 `navigator.language`
  - Done when：按钮切换后页面上中英 DOM 互相显隐；刷新后语言持久

- [x] **4.3 AICover 组件**
  - Req: REQ-07-3, REQ-07-6
  - 文件：`src/components/AICover.astro`
  - design §6.3 的 category → 色板映射；无封面图时渲染
  - Done when：不同 category 卡片颜色各异；有 cover 字段时优先显示真封面

- [x] **4.4 PostCard 组件**
  - Req: REQ-07-2
  - 文件：`src/components/PostCard.astro`
  - 结构：封面 / 分类 badge / 锁住 badge / 标题 / 摘要 / 标签 / 日期 / 阅读时长
  - 中英双份 DOM（`.lang-zh` / `.lang-en`）
  - 悬停上浮 + 轻微 shadow（CSS `transition` 即可，不必 Framer）
  - Done when：首页网格整齐，hover 效果自然

- [x] **4.5 FeaturedPost 组件**
  - Req: REQ-07-5（精选文章）
  - 文件：`src/components/FeaturedPost.astro`
  - 大卡片，左右分栏：左侧封面、右侧元信息
  - Done when：首页第一篇用这个组件展示

- [x] **4.6 Hero 组件**
  - Req: REQ-07-5（Hero 区域）
  - 文件：`src/components/Hero.astro` + `src/components/islands/TerminalAnim.tsx`
  - 左侧：品牌 "Xyvora" / 副标题 / 两个 CTA；右侧终端动画（React island，`client:visible`）
  - Done when：终端有跳动光标、渐变 glow 效果

- [x] **4.7 TOC 组件**
  - Req: REQ-07-4（TOC）
  - 文件：`src/components/TableOfContents.astro`
  - 从 `render(post).headings` 取 h1-h3；sticky；当前位置高亮（IntersectionObserver）
  - 支持中英切换时重建（从 `data-lang` 属性响应）
  - Done when：文章页右侧出现目录，点击跳转且高亮当前节

- [x] **4.8 MermaidIsland**
  - Req: REQ-05-10
  - 文件：`src/components/islands/MermaidIsland.tsx`
  - `client:visible` 时动态 `import('mermaid')` 并渲染页面上所有 `[data-mermaid]`
  - Done when：含 mermaid 的文章页渲染出图；不含 mermaid 的文章无 mermaid.js 加载

- [x] **4.9 CodeBlockWrapper**
  - Req: REQ-07-6（借鉴旧前端代码体验）
  - 文件：`src/components/CodeBlockWrapper.astro` + 对应 CSS
  - Shiki 已完成高亮；这里只补：语言标签栏 + 复制按钮 + 长代码折叠（>600px 加"展开"）
  - 以 rehype 插件方式包裹 `<pre>` 或用客户端 JS 在 mount 时包裹
  - Done when：每个代码块左上角显示语言、右上角有复制按钮

- [x] **4.10 ReadingProgress**
  - Req: REQ-07-4（进度条）
  - 文件：`src/components/ReadingProgress.astro`
  - 固定 top 的 1px 条；随 scroll 百分比变宽
  - Done when：长文滚动时进度条平滑增长

- [x] **4.11 返回顶部按钮**
  - Req: REQ-07-4（返回顶部）
  - 文件：`src/components/BackToTop.astro`
  - 滚动 > 400px 时 fade-in；点击 scrollTo top smooth
  - Done when：长文滚动时按钮出现

- [x] **4.12 SearchModal（Ctrl+K / ⌘+K）**
  - Req: REQ-07-5（全局搜索）
  - 文件：`src/components/SearchModal.astro`（外壳）+ 客户端脚本用 Fuse.js
  - 构建时把 slug / title / summary / tags / category 输出到 `/search-index.json`
  - 键盘快捷键全局绑定
  - 结果点击跳文章
  - Done when：Ctrl+K 打开；输入"htb"能搜到相关文章

- [x] **4.13 Giscus**
  - Req: REQ-07-4（评论）
  - 文件：`src/components/Giscus.astro`
  - design §11 的代码；主题随 `data-theme` 变化同步
  - Done when：文章页底部加载 Giscus iframe，切深浅色时 Giscus 跟着切

- [x] **4.14 LockedBanner**
  - Req: REQ-02-2
  - 文件：`src/components/LockedBanner.astro`
  - 复刻原 `post.html` 的 ACCESS DENIED 终端风格（见 §post.html L149-L163）
  - 中英文文案各一份
  - Done when：锁住的文章详情页显示 banner、无正文

- [x] **4.15 Header / Footer**
  - Req: REQ-07-5, REQ-07-9
  - 文件：`src/components/Header.astro`、`src/components/Footer.astro`
  - Header：Logo（Xyvora）、导航（Home / Archives / Tags / Categories / About）、主题切换、语言切换
  - Footer：版权 / GitHub / RSS 链接
  - Done when：品牌名 "Xyvora" 可见；导航链接全部可点

---

## Phase 5：页面

- [x] **5.1 BaseLayout**
  - Req: REQ-08-1 ~ REQ-08-12, REQ-11-5
  - 文件：`src/layouts/BaseLayout.astro`
  - design §5.1 完整实现：meta / OG / Twitter / canonical / GSC verification / CF Analytics / 主题初始化
  - Done when：每个页面的 `<head>` 都包含这些元素；GSC meta 由环境变量控制

- [x] **5.2 PostLayout**
  - Req: REQ-07-4
  - 文件：`src/layouts/PostLayout.astro`
  - 包含：顶部元信息、正文 slot、TOC、进度条、返回顶部、Giscus
  - Done when：文章页整体布局与 design §5.5 一致

- [x] **5.3 首页 `/`**
  - Req: REQ-07-5
  - 文件：`src/pages/index.astro`
  - 组件组合：Hero + SearchModal + FeaturedPost + 最新 PostCard 网格
  - Done when：本地 dev 访问 `/` 渲染正常

- [x] **5.4 文章页 `/post/<slug>/`**
  - Req: REQ-03-1, REQ-03-2, REQ-02-1 ~ REQ-02-5, REQ-11-3, REQ-11-4
  - 文件：`src/pages/post/[slug].astro`
  - design §5.4 实现，包括锁住判断、中英双份内容渲染、无英文版时 fallback
  - Done when：`/post/htb-bruno/` 可访问；锁住的文章显示 LockedBanner

- [x] **5.5 About 页**
  - Req: REQ-03-5
  - 文件：`src/pages/about.astro`
  - 基于旧 `templates/about.html` 视觉迁移（简化）
  - Done when：`/about/` 可访问

- [x] **5.6 Archives 页**
  - Req: REQ-03-5
  - 文件：`src/pages/archives.astro`
  - 按年月分组展示所有已发布文章
  - Done when：`/archives/` 显示"2026 年 1 月 | htb administrator / htb bruno..."

- [x] **5.7 Tags 页**
  - Req: REQ-03-5
  - 文件：`src/pages/tags/index.astro`、`src/pages/tags/[tag].astro`
  - 索引页按标签文章数排序；单标签页列出所有含该 tag 的文章
  - Done when：`/tags/` 和 `/tags/Windows/` 均可访问

- [x] **5.8 Categories 页**
  - Req: REQ-03-5
  - 文件：`src/pages/categories/index.astro`、`src/pages/categories/[name].astro`
  - 同 Tags 页结构
  - Done when：`/categories/` 和 `/categories/HTB/` 均可访问

- [x] **5.9 404 页**
  - Req: REQ-03-5
  - 文件：`src/pages/404.astro`
  - 复刻原 `templates/404.html` 的视觉
  - Done when：访问不存在页面返回 404 内容

- [x] **5.10 sitemap**
  - Req: REQ-08-5
  - 文件：`astro.config.mjs` 中的 `@astrojs/sitemap` integration 已注册
  - 过滤：不包含 `/404`
  - Done when：`/sitemap-index.xml` 可访问，包含所有文章 URL

- [x] **5.11 robots.txt**
  - Req: REQ-08-6, REQ-08-11
  - 文件：`public/robots.txt`（静态）
  - 内容：`User-agent: * / Allow: / / Sitemap: https://neobee.top/sitemap-index.xml`
  - Done when：`/robots.txt` 可访问

- [x] **5.12 RSS**
  - Req: REQ-08-7
  - 文件：`src/pages/rss.xml.ts`
  - design §10.3 实现，包含最新 20 篇
  - Done when：`/rss.xml` 返回合法 XML

- [x] **5.13 Schema.org JSON-LD**
  - Req: REQ-08-4
  - 位置：`src/layouts/PostLayout.astro` 里输出 `<script type="application/ld+json">`
  - 字段参照旧 `post.html` L40-L64
  - Done when：文章页 view-source 能看到 BlogPosting JSON-LD

---

## Phase 6：翻译脚本

- [x] **6.1 脚本依赖**
  - Req: REQ-13-8
  - 文件：`scripts/requirements.txt`
  - 内容：`openai>=1.0`、`python-frontmatter>=1.0`、`requests>=2.31`
  - Done when：`pip install -r scripts/requirements.txt` 成功

- [x] **6.2 frontmatter 工具**
  - Req: REQ-10-10
  - 文件：`scripts/lib/frontmatter.py`
  - 函数：`read_note(path) -> (fm, body)`、`write_note(path, fm, body)`
  - 用 `python-frontmatter` 但保持中文字段原名不变
  - Done when：读写同一文件内容无损

- [x] **6.3 source_hash 计算**
  - Req: REQ-10-5, REQ-10-6, REQ-10-7
  - 文件：`scripts/lib/hash_util.py`
  - design §7.3 实现
  - Done when：同一文件多次计算哈希一致；改动 `简介` 或 body 哈希变化；改动文件 `mtime` 不变哈希

- [x] **6.4 按标题切块**
  - Req: REQ-10-14
  - 文件：`scripts/lib/chunker.py`
  - design §7.4 实现
  - Done when：超长文本按 h1/h2 正确切分；短文不切

- [x] **6.5 LLM 客户端封装**
  - Req: REQ-10-13
  - 文件：`scripts/lib/llm_client.py`
  - `LlmClient.from_env()` 读 `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL`
  - 方法：`translate_chunk(system_prompt, content) -> (translated_text, tokens_used)`
  - 重试 3 次，指数退避
  - Done when：能成功调用一次返回翻译

- [x] **6.6 翻译主入口**
  - Req: REQ-10-1 ~ REQ-10-12
  - 文件：`scripts/translate.py`
  - design §7.1 完整实现：
    - 参数：`--vault` / `--force` / `--only` / `--dry-run`
    - 发布判定（§7.2）
    - 缓存命中跳过
    - 调用切块 + 翻译 + 组装 frontmatter（§7.6）
    - 失败不覆盖旧译文
    - 统计输出到 `GITHUB_STEP_SUMMARY`
  - Done when：
    - `python scripts/translate.py --vault ./vault --dry-run` 能列出待翻文件
    - `--only htb-bruno` 单独翻一篇成功写回 `.en.md`
    - 再跑一次无改动 → 报告 "cached"

- [x] **6.7 System Prompt 校准**
  - Req: REQ-10-9
  - 位置：`scripts/translate.py` 中的 system prompt 常量
  - design §7.5 的文案；做 3 次实测：
    1. HTB 长文（含代码块 / CVE / wikilink）
    2. 方法论短文（含 callout）
    3. 含 mermaid 图
  - 抽查代码块未被翻译、wikilink 未被改动
  - Done when：3 个样本翻译质量可接受

---

## Phase 7：CI/CD

- [ ] **7.1 vault-repo `notify.yml`**
  - Req: REQ-09-1, 防循环
  - 文件：`F:\Work\Obsidian\.github\workflows\notify.yml`
  - design §8.3 完整实现；`paths-ignore: '**/*.en.md'`
  - Done when：vault 推送一次非 `.en.md` 的 md 改动 → Actions 里能看到 `Notify site-repo` 运行成功

- [ ] **7.2 site-repo `build.yml`**
  - Req: REQ-09-2, REQ-09-3, REQ-09-6, REQ-09-7, REQ-09-8, REQ-09-9
  - 文件：`.github/workflows/build.yml`
  - design §8.1 完整实现：clone vault → translate → commit 回 vault → npm run build → rsync 到 VPS → docker compose reload → smoke test
  - Done when：手动触发（`workflow_dispatch`）能走完全流程，`neobee.top` 能看到占位页之后的真正站点

- [ ] **7.3 端到端测试**
  - Req: REQ-09-9
  - 操作：
    1. 在 Obsidian 里随便改一篇已发布文章（加一句"测试"）
    2. `git push` vault-repo
    3. 等 5 分钟
    4. 看 `notify.yml` 和 `build.yml` 都成功
    5. 访问 `https://neobee.top/post/<slug>/` 确认改动生效
    6. `ssh root@45.63.124.218 "ls /root/neobee-stack/Neobee714.github.io/"` 确认 `dist/` 和 `dist.old/` 都在
  - Done when：5 分钟内完成全链路，线上看到改动

---

## Phase 8：VPS 容器改造与域名

- [ ] **8.1 SSH 到 VPS，做一次性改造**
  - Req: REQ-13-4, REQ-13-5, REQ-13-10
  - 动作（按 design §9.5 逐项）：
    1. 清理 `/root/neobee-stack/Neobee714.github.io/` 旧 Flask 源码（Phase 0.7 已备份）
    2. 创建占位 dist（`<h1>Placeholder</h1>`）
    3. 写入 `nginx-site.conf`（内容见 design §9.3）
    4. 更新 `docker-compose.yml` 中 `neobee-blog` 服务定义（design §9.2）
    5. 更新 `nginx.conf` 中 `proxy_pass http://neobee-blog:5000` → `:80`（design §9.4）
    6. `docker compose up -d --no-deps neobee-blog && docker compose restart neobee-nginx`
    7. `curl -I https://neobee.top/` 应 200
  - Done when：`curl https://neobee.top/` 返回占位页 HTML

- [ ] **8.2 跑一次完整 CI 验证**
  - Req: REQ-09-9
  - 动作：手动触发 `build.yml` → 等完成
  - 访问 `https://neobee.top/` 应该从占位页变成 Astro 渲染的真实首页
  - Done when：整个流水线跑通，线上内容正确

- [ ] **8.3 启用 Cloudflare Web Analytics**
  - Req: —（替代旧 analytics.py）
  - 动作：
    1. CF Dashboard → Analytics & Logs → Web Analytics → Add a site → `neobee.top`
    2. 拿 beacon token 填 site-repo Secret `PUBLIC_CF_ANALYTICS_TOKEN`
    3. 触发一次重新构建（任意 push 或手动 workflow）
    4. 访问几次站点 → 面板里看到实时数据
  - Done when：CF Web Analytics 面板出现访问数据

- [ ] **8.4 绑定 Google Search Console**
  - Req: REQ-08-10, REQ-08-12
  - 动作：
    1. GSC → 添加资源 → `https://neobee.top` → 选 HTML 标记验证
    2. 复制 verification code → 填 site-repo Secret `GOOGLE_SITE_VERIFICATION`
    3. 触发重新构建
    4. GSC 点"验证" → 通过
    5. 提交 sitemap `https://neobee.top/sitemap-index.xml`
  - Done when：GSC 显示域名已验证 + sitemap 状态 "成功"

- [ ] **8.5 Giscus 配置（如已启用 Discussions）**
  - Req: REQ-07-4（评论）
  - 动作：
    1. `Neobee714.github.io` Settings → 勾选 Discussions
    2. 建分类（如 `Announcements`）
    3. giscus.app 取 repo_id / category / category_id
    4. 填 site-repo Secrets 的 3 个 `PUBLIC_GISCUS_*`
    5. 触发重新构建
  - Done when：文章页底部 Giscus iframe 正常显示

- [ ] **8.6 SEO 抽查**
  - Req: REQ-08-1 ~ REQ-08-9
  - 手工检查一篇文章的 view-source：
    - ✅ `<title>` / `<meta description>` / `<meta keywords>` 存在
    - ✅ OG 系列、Twitter Card
    - ✅ JSON-LD
    - ✅ canonical
  - 用 [Rich Results Test](https://search.google.com/test/rich-results) 验证 JSON-LD 无误
  - Done when：上面 4 项全绿

---

## Phase 9：质量保障

- [ ] **9.1 Lighthouse 跑分**
  - Req: REQ-12-3
  - 动作：Chrome DevTools → Lighthouse → 跑首页、1 篇文章页
  - 目标：Performance ≥ 90 / SEO ≥ 95 / Accessibility ≥ 90
  - 若不达标：查 `web.dev` 建议，典型问题是图片尺寸、字体加载、color contrast
  - Done when：3 个分数全达标

- [ ] **9.2 Obsidian 语法覆盖测试**
  - Req: REQ-05-1 ~ REQ-05-13
  - 在 vault 里准备一篇"语法测试"笔记（可参考 `F:\Work\Obsidian\类型.md`），设置 `发布: true`
  - 覆盖：标题 / 加粗 / 斜体 / 列表 / 任务列表 / 代码块 / 表格 / wikilink / embed / callout / LaTeX / mermaid / `==高亮==`
  - push → 等构建 → 访问该文章
  - Done when：每种语法都正确渲染，无破损或残留 Obsidian 语法

- [ ] **9.3 锁住 / 未发布 / 破链的边界测试**
  - Req: REQ-02-1 ~ REQ-02-5, REQ-01-2, REQ-05-3
  - 准备 4 篇测试笔记：
    - A: `发布:true` + `是否锁住:No` → 正常
    - B: `发布:true` + `是否锁住:Yes` → 列表可见，详情显示 LockedBanner
    - C: `发布:false` → 完全不出现
    - D: 含 `[[不存在的笔记]]` → 渲染为 `.wiki-link.broken`，构建日志 WARN
  - Done when：4 种情况行为符合需求

- [ ] **9.4 翻译流水线压测**
  - Req: REQ-09-8, REQ-10-6, REQ-10-11
  - 操作：
    1. 改一篇文章的 body → push → 查是否重新翻译（应该是 → `translated: 1`）
    2. 不改内容仅改 mtime → push → 查是否跳过（应该是 → `cached: 1`）
    3. 模拟 LLM 失败（把 `LLM_API_KEY` 设成错值）→ push → 查旧 `.en.md` 是否保留（应该是）
  - Done when：3 种场景行为正确

- [ ] **9.5 旧链接兼容性**
  - Req: REQ-03-1
  - 操作：在原 Notion 时代分享过的 URL 抽几条（如 `/post/htb-bruno`）访问新站
  - Done when：都能正常访问（302 或直接 200，无 404）

---

## Phase 10：清理

- [ ] **10.1 确认旧仓库 main 分支已替换**
  - Req: REQ-13-1, REQ-13-5
  - 动作：`git log origin/main --oneline -5` 确认顶部是 Astro 迁移的 commit，底部有 `legacy-flask-v1` tag
  - Done when：GitHub 仓库主页只见新项目

- [ ] **10.2 更新 README**
  - Req: REQ-08-12（GSC 文档）
  - 文件：`README.md`
  - 内容：
    - 项目简介（Xyvora，Astro 博客，源码公开 / 内容私仓）
    - 本地开发指令
    - 部署架构图（可引用 design §0.2）
    - Secrets 清单
    - GSC 验证步骤（REQ-08-12）
    - 如何添加 / 修改 / 删除文章（在 Obsidian 里 push 即可）
  - Done when：README 覆盖上述内容

- [ ] **10.3 删除残留的 legacy 引用**
  - Req: REQ-13-5, REQ-13-7
  - 动作：全局搜索 `Flask` / `Notion` / `notion-client` 关键字，确保代码里没有残留
  - Done when：`grep -r "notion" . --exclude-dir=.git --exclude-dir=vault` 无业务代码匹配

- [ ] **10.4 `.gitignore` 完善**
  - Req: —
  - 文件：site-repo 的 `.gitignore`
  - 至少包含：`node_modules`、`dist`、`.astro`、`.env`、`.DS_Store`
  - Done when：`git status` 干净

---

## 需求追溯矩阵（REQ → Tasks）

| Requirement | 覆盖任务 |
|---|---|
| REQ-01-* 核心工作流 | 0.1, 2.4, 7.1, 7.2, 7.3 |
| REQ-02-* 锁住可见性 | 2.4, 4.14, 5.4, 9.3 |
| REQ-03-* URL 与兼容 | 2.5, 5.4 ~ 5.9, 9.5 |
| REQ-04-* Frontmatter 映射 | 2.1, 2.2, 2.4, 2.6 |
| REQ-05-* Obsidian 语法 | 3.1 ~ 3.4, 4.8, 4.9, 9.2 |
| REQ-06-* 图片处理 | 3.5 |
| REQ-07-* 前端视觉 | 4.1 ~ 4.15, 5.1, 5.2, 5.3 |
| REQ-08-* SEO | 5.1, 5.10, 5.11, 5.12, 5.13, 8.4, 8.6 |
| REQ-09-* 自动化流水线 | 0.3, 0.4, 7.1, 7.2, 7.3, 8.1, 8.2 |
| REQ-10-* 翻译脚本 | 6.1 ~ 6.7, 9.4 |
| REQ-11-* 中英切换 | 4.2, 4.4, 5.4 |
| REQ-12-* 性能 | 9.1 |
| REQ-13-* 清理 | 0.5, 0.7, 1.1, 8.1, 10.1 ~ 10.4 |

---

## 里程碑建议

| 里程碑 | 包含阶段 | 预估工作量 |
|---|---|---|
| **M1：Hello Xyvora**（骨架跑通） | Phase 0 + 1 + 2 | 1 天 |
| **M2：文章能渲染** | Phase 3 + Phase 5（5.1 ~ 5.4） | 2 天 |
| **M3：UI 完整** | Phase 4 + Phase 5 剩余 | 2 天 |
| **M4：VPS 容器改造** | Phase 8.1 | 0.5 天（风险点在这里） |
| **M5：翻译 + CI 上线** | Phase 6 + 7 + 8.2 ~ 8.6 | 1.5 天 |
| **M6：质量 + 清理** | Phase 9 + 10 | 0.5 天 |

**总计约 7~8 个工作日**（单人 part-time）。

**关键风险节点**：M4 是第一次碰 VPS 生产容器，务必先在 Phase 0.7 备份到位。如果 M4 出问题，回滚路径是 `docker-compose.yml.pre-astro` + Flask tar 包。

---

## 下一步

按 Phase 0 的 4 个任务开始。等 Phase 0 全部 `[x]` 完成后，进入 Phase 1。

或者你告诉我"动手"，我直接从 **1.1 清空工作目录**开始执行。
