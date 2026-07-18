# Vault 内容源重构与英文功能移除设计

日期：2026-07-17
状态：设计与书面审核均已确认，待实施

## 背景

博客是 Astro 静态站点，文章来自独立的 Obsidian vault。现有实现把内容目录硬编码为 `SecNotes/` 和 `Translated/SecNotes/`，而 vault 已重组为新的主题目录。这导致本地构建可能找不到文章，同时构建仍能成功并产生空站点。

实际部署链路已通过代码和 VPS 只读检查确认：GitHub Actions 克隆 vault、构建 `dist/`，再通过 rsync 把静态产物发送到 VPS。VPS 上的 `neobee-blog` 是只读挂载 `dist/` 的 Nginx 容器，不负责拉取文章或执行 Astro 构建。

英文翻译功能不再需要。当前代码、脚本、CI 步骤和 vault 中的英文译文都应删除，但不重写 Git 历史。

## 目标

1. 中文文章可位于 vault 的任意用户内容目录，移动文件不影响发布。
2. 发布资格只由 frontmatter 决定，不再由 `SecNotes` 等目录名决定。
3. 未发布笔记和未被发布文章引用的资源不进入 Astro 内容集合或 `dist/`。
4. 路径错误、零文章、重复 Slug 等情况必须阻止部署。
5. 删除全部英文翻译功能、脚本、当前译文和有效配置引用。
6. 保持 GitHub Actions 构建并向 VPS 同步 `dist/` 的部署方式。

## 非目标

1. 不重写博客仓库或 vault 仓库的 Git 历史。
2. 不修改 VPS 的 Docker、Nginx、cron 或网络配置。
3. 不引入数据库、CMS 或运行时 Markdown 渲染。
4. 不重新设计博客页面视觉样式。
5. 不追溯改写已归档的旧设计文档；当前 README、项目说明和本设计必须反映新行为。

## 方案选择

采用自定义 Astro vault loader。loader 直接遍历 vault，先读取轻量 frontmatter，只把符合发布条件的中文文章送入 Astro Content Collections。

未采用以下方案：

- 全量 glob 后在页面过滤：会让私人笔记先进入内容系统，隔离不足。
- 构建前复制到中间目录：隔离清晰，但本地开发需要额外同步和监听机制。

## 内容发现架构

### Vault 根目录

`ASTRO_VAULT_PATH` 只表示 vault 根目录。它不能包含任何业务目录假设。

- 本地 Linux 示例：`/mnt/hgfs/Work/Obsidian`
- Windows 示例：`F:/Work/Obsidian`
- CI 示例：`${{ github.workspace }}/vault`

路径解析必须跨 Windows、WSL 和普通 Linux 工作，且在目标不存在时立即报错。

### 技术目录排除

为避免扫描工具状态和回收内容，以下目录始终排除，不属于“任意用户内容目录”：

- `.git/`
- `.obsidian/`
- `.trash/`
- `node_modules/`
- 名为 `Templates` 的模板目录

除此以外，文章所在业务目录不受限制。

### 发布判定

Markdown 必须同时满足：

1. frontmatter 中 `发布` 为 `true`、`yes` 或 `是`。
2. `Slug` 存在且去除首尾空白后非空。
3. `状态` 不是 `进行中`、`draft`、`wip` 或 `writing`。
4. 文件名不以 `.en.md` 结尾。

`是否锁住` 和 `状态: 已锁住/locked` 的现有语义保留：文章出现在列表、RSS 和 sitemap 中，但详情页不展示正文。

未设置 `发布` 的笔记不进入 Astro 集合。未发布笔记不执行完整 schema 校验，因此私人笔记中的自定义 frontmatter 不会阻塞博客构建。

### 标识与冲突

公开 URL 继续使用 `Slug`，文章物理路径不是公开标识。

- 任意两个已发布中文文章使用相同 `Slug` 时构建失败。
- `发布: true` 但缺少有效 `Slug` 时构建失败。
- 已发布文章的 frontmatter 无法解析或不符合 schema 时构建失败。
- 有效扫描范围内发现任何 `.en.md` 文件时构建失败，防止英文功能或旧产物意外恢复。

## 组件边界

### Vault 路径模块

职责：读取并规范化 `ASTRO_VAULT_PATH`，返回经过存在性和可读性验证的绝对路径。

消费者：内容 loader、Slug 检查、图片与 wikilink 解析。

### Vault 内容 loader

职责：遍历 Markdown、执行轻量发布判定、对候选文章做完整解析，并向 Astro 提供稳定的内容条目。

它是文章发现规则的唯一来源。独立的 Slug 检查集成若保留，必须复用同一规则模块，不能再次硬编码目录或发布值。

### 发布资源索引

职责：从已发布文章正文提取 wikilink 和本地资源引用，只解析这些被引用目标。

处理规则：

1. 外部 HTTP(S) 和 data URL 不处理。
2. 优先解析相对文章位置的资源。
3. Obsidian basename 引用可在 vault 中查找候选文件。
4. 同名候选超过一个且无法通过相对位置消歧时构建失败。
5. 只有最终被已发布文章引用的资源才复制到 `dist/_images`。

资源路径变化不会改变输出文件的稳定规范化名称。资源缺失时保留明确警告占位，不复制错误文件；资源歧义属于构建错误。

### 中文文章索引

`obsidian-parser` 只维护：

- 已发布文章列表
- `Slug -> Post` 映射

删除所有译文映射、语言匹配和 `getPostWithTranslation()`。

## 英文功能删除范围

### 博客 UI 和内容层

- 删除 `src/components/LangToggle.astro`。
- 从 Header 删除语言按钮。
- 删除首页、文章页、FeaturedPost 和 PostCard 的英文摘要、英文正文和 fallback。
- 删除 `lang-en`、`lang-zh`、语言状态和相关客户端事件处理。
- 从内容 schema 删除 `lang`、`source`、`source_hash`、`translated_at`。
- 从 loader、vault 索引和文章索引删除译文识别逻辑。

HTML 文档自身的 `lang="zh-CN"` 属于中文站点元数据，必须保留。

### 翻译工具链

删除仅为翻译服务的 Python 工具和依赖，包括：

- `scripts/translate.py`
- `scripts/translate_summary.py`
- `scripts/check_en_quality.py`
- `scripts/check_codeblocks.py`
- `scripts/lib/` 下的翻译、哈希、分块、frontmatter 和译文校验辅助代码
- `scripts/requirements.txt`
- 对应 Python 测试

若删除后 `scripts/` 为空，则删除整个目录。`package.json` 删除 Python 测试命令，只保留实际存在的测试套件。

### CI 与配置

- 删除 workflow 的翻译输入项。
- 删除 Python 安装和依赖安装步骤。
- 删除翻译及将 `.en.md` 提交回 vault 的步骤。
- 删除 `VAULT_PUSH_TOKEN`、`LLM_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL` 的代码和文档引用。
- 从本地 `.env` 删除不再使用的翻译凭据。
- GitHub 仓库中已保存但不再使用的翻译 Secrets 由仓库管理员在设置中移除。

`SITE_DISPATCH_TOKEN` 仍用于 vault 通知博客仓库，不属于翻译功能，必须保留。

### Vault 译文

删除 vault 当前工作树中的全部 `*.en.md` 文件。检查时共有 132 个文件，实施时以实际扫描结果为准。删除空的 `50-Published/Translated` 目录及其他仅存放译文的空目录。

这些是普通 Git 删除。旧提交仍可恢复译文，不执行 filter-repo、rebase 或强制推送。

## 数据流

1. 用户在 Obsidian 中编辑或移动中文 Markdown。
2. vault 仓库 push 到 GitHub。
3. vault workflow 对 Markdown 变化发送 `repository_dispatch`。
4. 博客 GitHub Actions checkout 站点并克隆 vault。
5. 自定义 loader 按 frontmatter 发现发布文章。
6. 构建前验证路径、文章数量、Slug 和资源引用。
7. Astro 生成首页、文章页、归档、分类、标签、搜索、RSS 和 sitemap。
8. 构建成功后 rsync `dist/` 到 VPS。
9. VPS 的 `neobee-blog` Nginx 容器继续只读提供 `dist/`。

由于 GitHub `paths` 过滤器不能读取 frontmatter，vault workflow 应监听所有用户 Markdown 变化。未发布笔记变化可能触发一次无内容变化的构建，但不会公开该笔记。

## 错误处理与部署保护

以下情况使 Astro 构建非零退出，后续 rsync 和容器重载不执行：

- vault 根目录缺失、不可读或不是目录
- 发布文章数量为 0
- 已发布文章缺少 Slug
- 已发布文章 Slug 重复
- 已发布文章 frontmatter 无法解析或 schema 无效
- 存在 `.en.md` 文件
- 本地资源引用存在多个无法消歧的候选

缺失但唯一命名的本地资源沿用可见占位和警告，避免一张图片使全部文章不可发布。该行为须在构建摘要中统计。

构建日志应输出扫描文件数、已发布文章数、跳过草稿数、缺失 Slug 数、复制资源数和缺失资源数，但不能输出私人笔记正文。

## 测试策略

### 单元测试

使用临时 vault fixture 覆盖：

- 发布值和草稿状态规范化
- 任意嵌套目录中的文章可被发现
- 移动文章后 Slug 和 URL 不变
- 未发布笔记不进入集合
- 缺失或重复 Slug 失败
- 零文章失败
- `.en.md` 存在时失败
- 相对资源解析、唯一 basename 解析和歧义失败
- 未引用资源不复制

### 组件与静态检查

- Header 不再引用 LangToggle。
- Homepage、PostCard、FeaturedPost 和文章页没有译文 props 或语言分支。
- `obsidian-parser` 不包含译文映射。
- CI 不包含 Python、翻译或 vault 写回步骤。
- 活跃代码和 README 不引用翻译环境变量。

### 集成验证

使用实际本地 vault 的正确 Linux 路径执行完整测试和生产构建，并确认：

- 生成至少一篇文章，且数量与 loader 报告一致
- `dist/post/` 存在文章路由
- 搜索索引、RSS 和 sitemap 包含文章
- 已发布文章图片存在于 `dist/_images`
- `dist` 不包含英文译文页面或私人未引用资源

不通过实际生产部署来验证代码；先在本地和 CI 完成验证，再由现有工作流部署。

## 迁移顺序

1. 为目录无关发现和失败保护添加失败测试。
2. 实现共享 vault 路径、发布规则和自定义 loader。
3. 将 Slug 检查、wikilink 和图片处理切换到共享规则。
4. 删除博客 UI、内容层和测试中的英文功能。
5. 删除 Python 翻译工具链并清理 package/CI/README 配置。
6. 在 vault 工作树中删除全部 `.en.md` 和空译文目录。
7. 更新 vault notify workflow，使目录移动后仍触发构建。
8. 对博客和 vault 分别检查 Git diff，避免混入无关用户改动。
9. 运行单元测试、生产构建和产物检查。
10. 博客仓库与 vault 仓库分别提交；不重写历史。

## 验收标准

1. 任意移动一篇 `发布: true` 的中文文章后，构建仍生成相同 Slug 页面。
2. 未发布笔记和未引用资源不出现在 `dist`。
3. 0 篇文章、重复 Slug、缺失 Slug 或残留 `.en.md` 会阻止部署。
4. 网站不显示语言切换或英文 fallback。
5. 博客仓库没有翻译脚本、翻译依赖或翻译 CI 步骤。
6. vault 当前工作树没有 `.en.md` 文件或译文目录。
7. VPS 继续只读提供 GitHub Actions 同步的 `dist`，无需配置变更。
