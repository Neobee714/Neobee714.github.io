---
inclusion: always
---

# Xyvora 项目 · AI 必读指引

> 你是一个正在协助迁移博客的 AI。**开始任何工作前，先读这份文档，再按需精读 `.kiro/specs/obsidian-blog-migration/` 下的三份文档。**

---

## 1. 一句话说明

把 `Neobee714.github.io` 从 **Flask + Notion API** 迁到 **Astro 静态站 + Obsidian 笔记源**，部署到现有的自建 VPS。品牌名叫 **Xyvora**。

---

## 2. 三份权威规范（改动前必读对应段落）

| 文档 | 路径 | 何时读 |
|---|---|---|
| 需求 | `.kiro/specs/obsidian-blog-migration/requirements.md` | 想知道某个行为"为什么要这样"时 |
| 设计 | `.kiro/specs/obsidian-blog-migration/design.md` | 动手前，尤其看目录结构、插件顺序、workflow YAML |
| 任务 | `.kiro/specs/obsidian-blog-migration/tasks.md` | 每次开工前对照找当前阶段与 Done when |

**顺序：** 先看 tasks 找到当前阶段 → 看 design 对应小节 → 遇到含糊再回 requirements 查 EARS 条款。

---

## 3. 项目基本事实（容易搞错的都列在这）

### 仓库

- **site-repo**: `Neobee714/Neobee714.github.io`（公开，本仓库）
  - 本地路径：`f:\Work\Program\Python\blog`
  - ⚠️ 仓库名虽然是 `.github.io` 后缀，**本项目不用 GitHub Pages**。部署目标是 VPS。
- **vault-repo**: `Neobee714/obsidian-vault`（私有）
  - 本地路径：`F:\Work\Obsidian`
  - 这是 Obsidian vault，存放 `SecNotes/` / `Templates/` / `assets/` 等
  - **不作为 submodule 加到 site-repo**；CI 里用 SSH deploy key 临时 clone

### 域名与部署

- 生产域名：`neobee.top`
- DNS：Cloudflare（**DNS only，灰云**，不启用橙云代理）
- 部署目标：VPS `45.63.124.218`
- Docker Compose 根目录：`/root/neobee-stack/`
- 前端静态文件目录：`/root/neobee-stack/Neobee714.github.io/dist/`
- VPS 有 5 个容器在跑：`neobee-db` / `neobee-redis` / `bookkeeping-backend` / `neobee-nginx` / `neobee-blog`
- 本次迁移**只改 `neobee-blog`**（从 Flask 换成 `nginx:alpine` 静态托管），其他容器不碰
- HTTPS：已由 `neobee-nginx` 容器 + Let's Encrypt 处理，**证书不要重新做**

### 关键凭据（不要把值写进代码或文档）

- `f:\Work\Program\Python\blog\.env` 里有全部密钥（已 gitignore，**永远不要 commit**）
- CI 用 GitHub Actions Secrets，不读 `.env`
- SSH key 文件（`$env:USERPROFILE\.ssh\` 下）：
  - `xyvora_ci_deploy`（私钥）→ 登 VPS 部署用
  - `vault_deploy`（私钥）→ 访问 obsidian-vault 用
  - **不要用 `id_rsa` / `id_ed25519`**（用户日常 key，别混）

---

## 4. 技术栈定稿（不要提议替换）

| 层 | 选型 |
|---|---|
| SSG | **Astro 5** |
| 样式 | Tailwind CSS + 自定义 CSS 变量（深浅色） |
| 代码高亮 | Shiki（Astro 内置） |
| 公式 | KaTeX |
| 图表 | Mermaid（客户端 `client:visible` 懒加载） |
| 翻译脚本 | Python 3.11 + `openai` SDK（OpenAI 兼容，通过 OpenRouter 中转） |
| 评论 | Giscus |
| 访问统计 | Cloudflare Web Analytics |
| CI | GitHub Actions |
| 部署 | rsync 到 VPS + `docker compose up -d --no-deps neobee-blog` |

---

## 5. 已经拒绝的方案（不要再提）

- ❌ Cloudflare Pages（用户改成了 VPS）
- ❌ GitHub Pages（只是仓库名碰巧这样）
- ❌ Vercel / Render / Railway（旧 Flask 时代用过，已弃用）
- ❌ Git Submodule 把 vault 塞进 site-repo（VPS 架构下没必要）
- ❌ 保留 Notion 作为后备源（干净迁移，彻底移除）
- ❌ Claude / Gemini 抽象层（只用 OpenAI 兼容接口）
- ❌ 英文版独立 URL `/post/<slug>/en/`（用户选了单页 CSS 切换）
- ❌ 用 `%20` 编码图片文件名空格（用户选了重命名为 `-`）
- ❌ VPS 自己跑 `npm run build`（构建放 GitHub Actions runner）

---

## 6. 架构决策速记

- **数据流**：Obsidian 写作 → push vault-repo → `repository_dispatch` → site-repo Actions clone vault + 翻译 + build + rsync → VPS 上的 `neobee-blog` 容器重载 → 线上更新
- **翻译产物位置**：`<原文>.en.md` 同目录写回 vault-repo（**不是放到 site-repo**）
- **翻译缓存**：用 `source_hash`（SHA-256 of frontmatter + body）判断是否跳过
- **中英切换**：`<html data-lang>` 属性 + CSS `.lang-zh` / `.lang-en` 显隐切换，同一个 HTML 文件里两份内容都有
- **锁住文章**：`是否锁住: Yes` 的文章仍在列表/sitemap/RSS 里，但详情页显示 "ACCESS DENIED" 占位，隐藏正文
- **发布过滤**：frontmatter `发布: true` 才进站，`状态: 进行中` 视为草稿（即使 `发布: true`）
- **URL 不变**：文章 URL 依旧是 `https://neobee.top/post/<Slug>/`，Slug 来自 frontmatter

---

## 7. 工作原则

1. **先读再动**：改任何配置前对照 design.md 的对应章节
2. **小步提交**：一个 Phase 内的任务尽量分开 commit
3. **不自作主张换工具**：用户已经在需求阶段拍板，除非有硬技术原因（比如依赖不兼容）
4. **VPS 是生产环境**：动它前先确认备份还在（`/root/neobee-stack/docker-compose.yml.pre-astro` 等）
5. **失败快速汇报**：命令报错直接把原始输出贴给用户，不要臆测原因
6. **不要 echo 敏感值**：`.env` 内容、PAT、SSH 私钥、API key 不要回显到对话或日志
7. **可逆优先**：能 revert 的改动随便做，不可逆的（删文件、docker rm、force push）先跟用户确认
8. **性能预算**：文章页首屏 JS ≤ 150KB gzip；首页 LCP ≤ 2.5s；不要随便加大库
9. **回答与写作**：中文沟通；代码注释和 commit message 用英文；响应要简洁，别凑字数

---

## 8. 当前进度

**Phase 0 已完成**：Secrets、SSH key、legacy tag、VPS 备份都到位。

**下一步**：Phase 1（site-repo 骨架初始化）—— 参见 `tasks.md` Phase 1。

> 如果用户说"继续"或"开始 Phase N"，先 `read_file` 看 tasks.md 对应小节的 Done when 标准，再动手。

---

## 9. 常见翻车场景与自救

| 症状 | 可能原因 | 速查 |
|---|---|---|
| `ssh: invalid format` | 默认 `~/.ssh/id_rsa` 格式老 | 显式 `-i ~/.ssh/xyvora_ci_deploy` 指定 key |
| CI workflow 里 `ASTRO_VAULT_PATH` 不存在 | 忘了在 build step 传环境变量 | 见 design.md §8.1 yaml |
| 图片 404 | 文件名含空格/中文未规范化 | 见 design.md §4.6 |
| wikilink 渲染为空 | 预扫 vault 时没建起映射表 | `globalThis.__wikilinkMap` 是否为空 |
| `neobee.top` 502 | `nginx.conf` 反代目标端口没改 5000→80 | 见 design.md §9.4 |
| 翻译无限循环 | vault push 触发→commit 译文→再 push | 确认 `paths-ignore: '**/*.en.md'` 生效 |

---

## 10. 与用户协作的边界

- **用户愿意做**：浏览器 UI 操作（GitHub Secrets、Cloudflare 面板、GSC 验证）、SSH key 生成、最终审核
- **你负责做**：所有代码编写、文档撰写、命令执行、目录建立、配置文件生成
- **需要先问再做**：force push、rm -rf、删容器、改 `neobee-nginx` 配置、改 bookkeeping 相关文件

---

_这份文档是"入门速查"。深度问题永远去三份规范里找权威答案。_
