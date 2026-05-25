# 设计文档：Xyvora（Obsidian → Astro 博客）

> 对应 `requirements.md`。需求决策已全部固化，本文档专注"**怎么做**"。

---

## 0. 总览

### 0.1 仓库与基础设施（已敲定）

| 角色 | 载体 | 可见性 | 说明 |
|---|---|---|---|
| vault-repo | [`Neobee714/obsidian-vault`](https://github.com/Neobee714/obsidian-vault) | 私有 | 存放整个 Obsidian vault；deploy key 已就绪 |
| site-repo  | [`Neobee714/Neobee714.github.io`](https://github.com/Neobee714/Neobee714.github.io) | 公开 | 存放 Astro 源码、翻译脚本、CI 配置 |
| 部署目标 | VPS `45.63.124.218` (Ubuntu 24.04) | — | 现有 Docker Compose 栈 `/root/neobee-stack/`；`neobee-nginx` 反代 + Let's Encrypt 证书已配好 |
| DNS | Cloudflare（DNS only，不启用橙云代理） | — | `neobee.top` A 记录指 `45.63.124.218` |
| 生产域名 | `neobee.top` | — | HTTPS 由 VPS 上的 `neobee-nginx` 终结 |

**VPS 现状复盘（SSH 已检视）：**

```
/root/neobee-stack/
├── docker-compose.yml          ← 含 5 个服务
├── nginx.conf                  ← neobee-nginx 容器的反代配置
├── certbot/                    ← Let's Encrypt 证书
├── Neobee714.github.io/        ← 当前 Flask 博客源码（本次迁移对象）
├── bookkeeping/                ← 记账应用（与本次迁移无关）
└── deploy.sh                   ← 仅 bookkeeping 用
```

现有 compose 服务：

| 容器 | 角色 | 本次迁移影响 |
|---|---|---|
| `neobee-db` (postgres) | bookkeeping 持久化 | 不变 |
| `neobee-redis` | bookkeeping 缓存 | 不变 |
| `bookkeeping-backend` | bookkeeping API | 不变 |
| `neobee-nginx` (nginx:alpine) | 所有 443 流量入口，证书、反代 | **不变**（这是迁移的核心前提） |
| `neobee-blog` (Flask + gunicorn) | 当前博客后端 | **本次改造目标** |

### 0.2 数据流全景

```
┌────────────────────┐   git push   ┌──────────────────────────┐
│ Obsidian 本地编辑  │ ───────────► │ Neobee714/obsidian-vault │
│ F:\Work\Obsidian   │              │  SecNotes/ Templates/... │
└────────────────────┘              └──────┬───────────────────┘
                                           │ repository_dispatch
                                           │ (event: vault-updated)
                                           ▼
┌──────────────────────────────────────────────────────────────┐
│ GitHub Actions (Neobee714.github.io)                         │
│  .github/workflows/build.yml                                 │
│                                                              │
│  ① checkout site-repo                                        │
│  ② SSH clone obsidian-vault  → ./vault/                      │
│  ③ python scripts/translate.py --vault ./vault               │
│       · 扫描 发布:true 的 .md                                │
│       · 按 source_hash 判断缓存                              │
│       · 调 OpenAI 兼容 API 翻译 → 写 .en.md                  │
│  ④ 若有新 .en.md → 用 PAT commit 回 vault-repo              │
│  ⑤ npm run build  (Astro)                                    │
│       · 扫 ./vault/**/*.md → HTML + _images/                 │
│       · 产出 dist/                                           │
│  ⑥ rsync -avz --delete dist/  root@45.63.124.218:            │
│       /root/neobee-stack/Neobee714.github.io/dist/           │
│  ⑦ ssh root@45.63.124.218                                    │
│       cd /root/neobee-stack                                  │
│       docker compose up -d --no-deps --build neobee-blog     │
└──────────────────────────────────────────────────────────────┘
                                           │
                                           ▼
┌──────────────────────────────────────────────────────────────┐
│ VPS (45.63.124.218)                                          │
│                                                              │
│  neobee-blog (nginx:alpine，挂载 dist/)                       │
│       ↑ expose :80                                           │
│       │                                                      │
│  neobee-nginx (nginx:alpine)   ← 已有 / 不变                 │
│       · 443 → proxy_pass http://neobee-blog:80              │
│       · Let's Encrypt 证书                                   │
└──────────────────────────────────────────────────────────────┘
                                           │
                                           ▼
                                  https://neobee.top/
```

### 0.3 技术栈定稿

| 层 | 选型 | 版本建议 |
|---|---|---|
| 站点生成 | Astro | ^5.0 |
| 样式 | Tailwind CSS v4 + 自定义 tokens | ^4.0 |
| 动效 | Framer Motion | ^11 |
| 图标 | lucide-react（按需引入）+ 少量 SVG | 最新 |
| 代码高亮 | Shiki（Astro 内置，构建时高亮、零运行时 JS） | 内置 |
| 数学公式 | KaTeX（rehype-katex） | ^0.16 |
| 图表 | Mermaid（客户端岛屿加载） | ^11 |
| 翻译脚本 | Python 3.11+ | — |
| 翻译 SDK | `openai` | ^1.0 |
| frontmatter 解析（Python） | `python-frontmatter` | ^1.0 |
| 部署 | VPS + Docker Compose（Nginx:alpine 静态服务 + 现有反代） | — |
| 评论 | Giscus | — |
| 访问统计 | Cloudflare Web Analytics | — |

### 0.4 关键决策回顾

- **双仓库**：`Neobee714/obsidian-vault`（私）+ `Neobee714/Neobee714.github.io`（公）
- **翻译产物**：`<原文>.en.md` 同目录写回 vault-repo
- **英文渲染**：单页 CSS 切换（中文 DOM + 英文 DOM 同时输出，根元素属性切换可见性）
- **图片文件名**：构建时规范化（空格 / 中文 → ASCII）
- **LLM**：只用 OpenAI 兼容接口
- **跨仓触发**：GitHub `repository_dispatch`
- **部署方式**：GitHub Actions 构建 → rsync `dist/` → VPS → 容器重载
- **VPS 现有基础设施不动**：`neobee-nginx` 反代、Let's Encrypt 证书、bookkeeping 栈 全部保留

---

## 1. 仓库初始化与迁移步骤

### 1.1 归档现仓库

```bash
# 在 f:\Work\Program\Python\blog 执行
git add -A && git commit -m "chore: final Flask/Notion snapshot before migration"
git tag legacy-flask-v1
git push origin main --tags
```

之后该目录下除 `.git/` 和 `.kiro/` 之外的文件**全部删除**。`.kiro/specs/obsidian-blog-migration/` 的三份文档（requirements、design、tasks）会跟随 site-repo 的初始化被移过去。

### 1.2 整理 vault-repo（已存在：`Neobee714/obsidian-vault`）

1. 仓库已创建为私有 ✅，deploy key 已生成 ✅
2. 如果 `F:\Work\Obsidian` 还没和这个远程仓库对齐，首次同步：
   ```bash
   cd F:\Work\Obsidian
   # 如果还没 init 过 git
   git init
   git branch -M main
   git remote add origin git@github.com:Neobee714/obsidian-vault.git
   # .gitignore（防止 Obsidian 工作区脏数据进仓）
   echo .obsidian/workspace*.json > .gitignore
   echo .trash/ >> .gitignore
   git add -A
   git commit -m "chore: initial vault import"
   git push -u origin main
   ```
3. 在 vault-repo Settings → Deploy keys 确认 deploy key 已添加（**只勾 Allow read access**，翻译脚本写回用另一个 PAT）
4. 添加 workflow `F:\Work\Obsidian\.github\workflows\notify.yml`（见 §8.3）

### 1.3 整理 site-repo（已存在：`Neobee714/Neobee714.github.io`）

> ⚠️ 当前 site-repo **main 分支**是旧 Flask 代码（也就是 VPS `/root/neobee-stack/Neobee714.github.io/` 目录的源头）。迁移策略：
>
> - 先在 site-repo 打 `legacy-flask-v1` tag 归档
> - 清空 main 分支，推送新 Astro 项目
> - VPS 上的 `/root/neobee-stack/Neobee714.github.io/` 本次迁移后**不再是 Flask 源码 clone**，而是容器挂载静态文件的工作目录（见 §8 与 §9）

在 `f:\Work\Program\Python\blog` 原地重建：

```bash
cd f:\Work\Program\Python\blog

# 1. 打 legacy tag 归档现有 Flask 代码
git add -A && git commit -m "chore: final Flask/Notion snapshot"
git tag legacy-flask-v1
git push origin main --tags

# 2. 清空工作目录（保留 .git 和 .kiro）
#    Windows cmd:
for /d %i in (*) do @if /i not "%i"==".git" if /i not "%i"==".kiro" rmdir /s /q "%i"
for %i in (*) do @del /q "%i"
#    （.git 和 .kiro 会被保留）

# 3. 初始化 Astro
npm create astro@latest . -- --template minimal --typescript strict --git no --install no

# 4. 安装依赖
npm install
npm install @astrojs/tailwind @astrojs/sitemap @astrojs/rss @astrojs/mdx @astrojs/react
npm install tailwindcss @tailwindcss/typography
npm install rehype-katex rehype-slug rehype-autolink-headings remark-math
npm install unist-util-visit unist-util-remove
npm install framer-motion lucide-react react react-dom
npm install fuse.js
npm install -D @types/react @types/react-dom

# 5. 提交并 force-push 到 main（覆盖旧的 Flask 代码）
git add -A
git commit -m "feat: migrate to Astro + Obsidian vault"
git push origin main --force-with-lease
```

### 1.4 配 Secrets

> ⚠️ **关于 PAT**：你已有一个 **classic PAT**（范围 `repo`）。由于 classic PAT 对账户下所有仓库有读写权，**下表中的 `VAULT_PUSH_TOKEN` 可直接复用这一个 PAT 值**。

**site-repo（`Neobee714.github.io`）Secrets：**

| Secret | 用途 | 值 |
|---|---|---|
| `VAULT_SSH_KEY` | 用 SSH clone 私仓 | `obsidian-vault` deploy key 的**私钥**（你已获得） |
| `VAULT_PUSH_TOKEN` | commit 翻译产物回 `obsidian-vault` | 你的 classic PAT |
| `VPS_SSH_KEY` | rsync + docker reload 用的专用 CI key 私钥 | 详见 §1.5 生成步骤 |
| `VPS_HOST` | VPS 地址 | `45.63.124.218` |
| `VPS_USER` | VPS 部署用户 | `root`（当前栈在 root 下） |
| `VPS_PATH` | VPS 上 dist 挂载目录 | `/root/neobee-stack/Neobee714.github.io/dist` |
| `VPS_COMPOSE_DIR` | VPS 上 compose 目录 | `/root/neobee-stack` |
| `LLM_API_KEY` | OpenAI 兼容密钥 | 你的 key |
| `LLM_BASE_URL` | 接口地址 | 如 `https://api.openai.com/v1` |
| `LLM_MODEL` | 模型名 | 如 `gpt-4o-mini` |
| `GOOGLE_SITE_VERIFICATION` | GSC 验证 | GSC 给你的 code |
| `PUBLIC_CF_ANALYTICS_TOKEN` | Cloudflare Web Analytics | 从 CF Dashboard 取 |
| `PUBLIC_GISCUS_REPO_ID` | Giscus | 从 giscus.app 取 |
| `PUBLIC_GISCUS_CATEGORY` | Giscus | 同上 |
| `PUBLIC_GISCUS_CATEGORY_ID` | Giscus | 同上 |

**vault-repo（`obsidian-vault`）Secrets：**

| Secret | 用途 | 值 |
|---|---|---|
| `SITE_DISPATCH_TOKEN` | vault push 后通知 site-repo 触发构建 | 你的 classic PAT |

### 1.5 生成 CI 专用 VPS SSH key

**不要复用你本地日常用的 SSH key。** 专门给 CI 签一把只做部署用的 ed25519 key：

```bash
# Windows (Git Bash 或 PowerShell)
ssh-keygen -t ed25519 -C "xyvora-ci-deploy" -f $env:USERPROFILE\.ssh\xyvora_ci_deploy -N '""'

# 将公钥追加到 VPS
Get-Content $env:USERPROFILE\.ssh\xyvora_ci_deploy.pub | ssh root@45.63.124.218 "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"

# 验证能用
ssh -i $env:USERPROFILE\.ssh\xyvora_ci_deploy root@45.63.124.218 "echo OK && docker --version"
```

然后把**私钥**（`xyvora_ci_deploy` 不带 `.pub` 那个）整段内容粘贴到 site-repo 的 `VPS_SSH_KEY` Secret。

**可选的加固**：VPS 的 `~/.ssh/authorized_keys` 里，把刚加的那行改为只允许部署命令：

```
command="/root/neobee-stack/deploy-blog.sh",no-port-forwarding,no-X11-forwarding,no-agent-forwarding ssh-ed25519 AAAA... xyvora-ci-deploy
```

配合 `/root/neobee-stack/deploy-blog.sh`（见 §8.4）限制 CI key 只能执行部署脚本，防止被滥用。此加固为可选项。

> **未来想强化安全性**：可改用 fine-grained PAT，为 `obsidian-vault` 单独签发只针对该仓库的 token，替换 `VAULT_PUSH_TOKEN`。

Cloudflare Pages 侧的 env vars（构建时需要的）：

| 变量 | 值 |
|---|---|
| `PUBLIC_SITE_URL` | `https://neobee.top` |
| `PUBLIC_GISCUS_REPO` | `<你>/xyvora-site` |
| `PUBLIC_GISCUS_REPO_ID` | Giscus 初始化时给的 |
| `PUBLIC_GISCUS_CATEGORY` | 同上 |
| `PUBLIC_GISCUS_CATEGORY_ID` | 同上 |
| `PUBLIC_CF_ANALYTICS_TOKEN` | Cloudflare Web Analytics token |
| `GOOGLE_SITE_VERIFICATION` | GSC code |

> `PUBLIC_` 前缀是 Astro 约定：会暴露到浏览器端；无前缀的只在构建期可用。

---

## 2. site-repo 项目结构

```
xyvora-site/
├── .github/workflows/
│   └── build.yml                      ← 触发、翻译、构建、部署
├── .kiro/
│   └── specs/obsidian-blog-migration/
│       ├── requirements.md
│       ├── design.md                  ← 本文档
│       └── tasks.md                   ← 下一步产出
├── public/
│   ├── favicon.svg
│   ├── robots.txt                     ← 手写（非模板）
│   └── avatar.jpg
├── scripts/
│   ├── translate.py                   ← LLM 翻译入口
│   ├── requirements.txt               ← openai / python-frontmatter / requests
│   └── lib/
│       ├── frontmatter.py             ← 解析与写回
│       ├── chunker.py                 ← 按标题切块
│       ├── llm_client.py              ← OpenAI 封装
│       └── hash_util.py               ← source_hash
├── src/
│   ├── content/
│   │   ├── config.ts                  ← Content Collections schema（Zod）
│   │   └── posts/                     ← ⚠ 不存实际 .md（CI 中指向 vault/）
│   ├── lib/
│   │   ├── obsidian-parser.ts         ← frontmatter 归一化 + 过滤
│   │   ├── remark-wikilink.ts         ← [[note]] / ![[img]]
│   │   ├── remark-callout.ts          ← > [!note] → <aside class="callout">
│   │   ├── remark-mermaid.ts          ← ```mermaid 代码块 → <MermaidIsland>
│   │   ├── remark-dataview-strip.ts   ← 忽略 Dataview / Templater 块
│   │   ├── rehype-image-rewrite.ts    ← 图片路径归一化
│   │   ├── reading-time.ts
│   │   ├── date-parser.ts             ← 支持 "2026年1月3日"
│   │   ├── site-meta.ts               ← 站点元数据
│   │   └── cover.ts                   ← AI Cover 生成（SSR 渲染为 PNG，仅用于 og:image）
│   ├── components/
│   │   ├── Header.astro
│   │   ├── Footer.astro
│   │   ├── PostCard.astro
│   │   ├── FeaturedPost.astro
│   │   ├── Hero.astro
│   │   ├── AICover.astro
│   │   ├── TableOfContents.astro
│   │   ├── ReadingProgress.astro
│   │   ├── ThemeToggle.astro          ← 深浅色
│   │   ├── LangToggle.astro           ← 中英切换
│   │   ├── SearchModal.astro          ← Ctrl+K
│   │   ├── Giscus.astro
│   │   ├── CopyCodeButton.astro
│   │   ├── CodeBlockWrapper.astro
│   │   ├── LockedBanner.astro         ← ACCESS DENIED
│   │   ├── Callout.astro
│   │   └── islands/
│   │       ├── MermaidIsland.tsx      ← client:visible
│   │       └── TerminalAnim.tsx       ← Hero 右侧终端动画
│   ├── layouts/
│   │   ├── BaseLayout.astro           ← <head>、主题初始化、GSC meta、CF analytics
│   │   └── PostLayout.astro           ← 文章页骨架
│   ├── pages/
│   │   ├── index.astro                ← 首页（列表 + Hero）
│   │   ├── about.astro
│   │   ├── archives.astro
│   │   ├── tags/
│   │   │   ├── index.astro
│   │   │   └── [tag].astro
│   │   ├── categories/
│   │   │   ├── index.astro
│   │   │   └── [name].astro
│   │   ├── post/
│   │   │   └── [slug].astro           ← 文章详情
│   │   ├── 404.astro
│   │   ├── sitemap-index.xml.ts       ← 由 @astrojs/sitemap 生成
│   │   └── rss.xml.ts                 ← 由 @astrojs/rss 生成
│   ├── styles/
│   │   ├── global.css                 ← Tailwind + 全局变量
│   │   ├── theme.css                  ← 深浅色 CSS 变量定义
│   │   ├── prose.css                  ← 正文样式（继承旧 base.css 精华）
│   │   └── callout.css
│   └── env.d.ts
├── astro.config.mjs
├── tailwind.config.ts
├── tsconfig.json
├── package.json
└── README.md
```

> **为什么 `src/content/posts/` 是空的？** 参见 §3 的设计，我们不把 markdown 静态地放进 site-repo；CI 里通过一个 hook 把 `./vault/SecNotes/` 的 `.md` 软链接（或拷贝）到这个目录，Content Collections 就能扫到。本地开发时用 `ASTRO_VAULT_PATH=F:/Work/Obsidian` 环境变量指向你的本地 vault。

---

## 3. 数据模型

### 3.1 Content Collections schema

`src/content/config.ts`：

```ts
import { defineCollection, z } from 'astro:content';

// 灵活的布尔解析：支持 true/false、'true'/'false'、'是'/'否'、'Yes'/'No'
const flexBool = z.preprocess((v) => {
  if (typeof v === 'boolean') return v;
  if (typeof v === 'string') {
    const s = v.trim().toLowerCase();
    if (['true', 'yes', '是', 'y', '1', 'locked'].includes(s)) return true;
    if (['false', 'no', '否', 'n', '0', ''].includes(s)) return false;
  }
  return false;
}, z.boolean());

// 灵活日期：支持 ISO、'2026年1月3日'、'2026/1/3'；否则用文件 mtime（在 parser 里兜底）
const flexDate = z.preprocess((v) => {
  if (v instanceof Date) return v;
  if (typeof v === 'string') {
    // 交给 src/lib/date-parser.ts 处理（见 §3.2）
    const d = parseFlexDate(v);
    if (d) return d;
  }
  return undefined;
}, z.date());

const postsCollection = defineCollection({
  type: 'content',
  schema: z.object({
    // —— 必需字段（缺失则跳过发布）——
    Slug: z.string().min(1),
    发布: flexBool,

    // —— 可选元数据 ——
    是否锁住: flexBool.optional().default(false),
    日期: flexDate.optional(),
    类型: z.string().optional(),
    难度: z.string().optional(),
    操作系统: z.string().optional(),
    简介: z.string().optional(),
    tags: z.array(z.string()).or(z.string()).optional().transform(normalizeTags),
    状态: z.string().optional(),

    // —— 翻译产物专用 ——
    lang: z.enum(['zh', 'en']).optional(),
    source: z.string().optional(),
    source_hash: z.string().optional(),
    translated_at: z.string().optional(),
  }),
});

export const collections = { posts: postsCollection };

function normalizeTags(v: unknown): string[] {
  if (Array.isArray(v)) return v.map(String).map((t) => t.trim()).filter(Boolean);
  if (typeof v === 'string') {
    return v.split(/[,，;；\s]+/).map((t) => t.trim()).filter(Boolean);
  }
  return [];
}
```

### 3.2 日期解析器

`src/lib/date-parser.ts`：

```ts
const CHINESE_DATE = /^(\d{4})年(\d{1,2})月(\d{1,2})日?$/;
const SLASH_DATE  = /^(\d{4})[\/\-](\d{1,2})[\/\-](\d{1,2})$/;

export function parseFlexDate(s: string): Date | undefined {
  const iso = new Date(s);
  if (!Number.isNaN(iso.getTime())) return iso;

  let m = s.match(CHINESE_DATE) || s.match(SLASH_DATE);
  if (m) {
    const [, y, mo, d] = m;
    return new Date(Date.UTC(+y, +mo - 1, +d));
  }
  return undefined;
}
```

### 3.3 发布过滤管道

在 `src/lib/obsidian-parser.ts` 里暴露一个总入口：

```ts
import { getCollection } from 'astro:content';

export async function getPublishedPosts() {
  const all = await getCollection('posts');

  // ① 只保留 发布:true
  const published = all.filter((p) => p.data['发布'] === true);

  // ② 去重：同一 Slug 只能出现一次（除了 .en.md 的翻译）
  // .en.md 的 id 是 "xxx.en"，原文是 "xxx"，只保留原文进列表
  const originals = published.filter((p) => p.data.lang !== 'en');

  // ③ 按日期倒序
  originals.sort((a, b) => {
    const da = a.data['日期']?.getTime() ?? 0;
    const db = b.data['日期']?.getTime() ?? 0;
    return db - da;
  });

  return originals;
}

export async function getPostWithTranslation(slug: string) {
  const all = await getCollection('posts');
  const zh = all.find((p) => p.data['Slug'] === slug && p.data.lang !== 'en');
  const en = all.find((p) => p.data.lang === 'en' && p.data.source?.includes(slug));
  return { zh, en };
}
```

### 3.4 同一 Slug 冲突检测

构建时在一个 Astro integration 里做断言：

```ts
// astro.config.mjs 里注册
export function slugUniquenessCheck() {
  return {
    name: 'slug-uniqueness',
    hooks: {
      'astro:build:setup': async () => {
        const posts = await getPublishedPosts();
        const seen = new Map<string, string>();
        for (const p of posts) {
          const slug = p.data['Slug'];
          if (seen.has(slug)) {
            throw new Error(
              `Duplicate Slug "${slug}" in ${p.id} and ${seen.get(slug)}`
            );
          }
          seen.set(slug, p.id);
        }
      },
    },
  };
}
```

---

## 4. Markdown 渲染管道

### 4.1 Astro 配置

`astro.config.mjs`：

```js
import { defineConfig } from 'astro/config';
import tailwind from '@astrojs/tailwind';
import mdx from '@astrojs/mdx';
import sitemap from '@astrojs/sitemap';
import react from '@astrojs/react';

import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import rehypeSlug from 'rehype-slug';
import rehypeAutolinkHeadings from 'rehype-autolink-headings';

import { remarkWikilink } from './src/lib/remark-wikilink.js';
import { remarkCallout } from './src/lib/remark-callout.js';
import { remarkMermaid } from './src/lib/remark-mermaid.js';
import { remarkDataviewStrip } from './src/lib/remark-dataview-strip.js';
import { rehypeImageRewrite } from './src/lib/rehype-image-rewrite.js';
import { slugUniquenessCheck } from './src/lib/integrations/slug-check.js';

export default defineConfig({
  site: 'https://neobee.top',
  integrations: [
    tailwind({ applyBaseStyles: false }),
    mdx(),
    react(),
    sitemap({
      filter: (page) => !page.includes('/404'),
    }),
    slugUniquenessCheck(),
  ],
  markdown: {
    remarkPlugins: [
      remarkDataviewStrip,    // 先去掉 dataview / templater 代码块
      remarkCallout,          // > [!note] → callout 节点
      remarkWikilink,         // [[note]] / ![[img]] → 自定义节点
      remarkMermaid,          // ```mermaid → MermaidIsland
      remarkMath,
    ],
    rehypePlugins: [
      rehypeSlug,
      [rehypeAutolinkHeadings, { behavior: 'wrap' }],
      rehypeKatex,
      rehypeImageRewrite,     // 最后改写所有 <img src> 到归一化路径
    ],
    shikiConfig: {
      themes: {
        light: 'github-light',
        dark: 'github-dark-dimmed',
      },
      wrap: true,
    },
  },
});
```

### 4.2 Wikilink 插件设计

`src/lib/remark-wikilink.ts`：

处理两种语法：
- `![[file.png]]` / `![[file.png|300]]` / `![[file.png|300x200]]` → `<img>`（交给 §4.6 resolve 路径）
- `[[note-name]]` / `[[note-name|显示文字]]` / `[[note#heading]]` → `<a>`

```ts
import { visit } from 'unist-util-visit';

const WIKILINK = /(!?)\[\[([^\]|#]+)(?:#([^\]|]+))?(?:\|([^\]]+))?\]\]/g;

export function remarkWikilink() {
  return (tree, file) => {
    visit(tree, 'text', (node, index, parent) => {
      const value = node.value;
      if (!WIKILINK.test(value)) return;
      WIKILINK.lastIndex = 0;

      const children = [];
      let lastIdx = 0;
      let match;
      while ((match = WIKILINK.exec(value)) !== null) {
        const [full, bang, target, heading, label] = match;
        // 前段普通文本
        if (match.index > lastIdx) {
          children.push({ type: 'text', value: value.slice(lastIdx, match.index) });
        }

        if (bang === '!') {
          // 图片嵌入
          const [name, sizeSpec] = target.split('|');
          const hast = {
            type: 'html',
            value: renderImageEmbed(name, label /* size hint */, file),
          };
          children.push(hast);
        } else {
          // wiki 内链
          const slug = resolveWikilink(target, file);
          children.push({
            type: 'link',
            url: slug ? `/post/${slug}${heading ? '#' + slugify(heading) : ''}` : '#',
            data: {
              hProperties: {
                className: slug ? 'wiki-link' : 'wiki-link broken',
                'data-broken': slug ? undefined : 'true',
                title: slug ? target : `未发布或不存在：${target}`,
              },
            },
            children: [{ type: 'text', value: label || target }],
          });
        }
        lastIdx = match.index + full.length;
      }
      if (lastIdx < value.length) {
        children.push({ type: 'text', value: value.slice(lastIdx) });
      }
      parent.children.splice(index, 1, ...children);
      return index + children.length;
    });
  };
}
```

`resolveWikilink` 需要在构建前预先扫一遍 vault，把所有 `发布:true` 文章的文件名（不含 `.md`）→ slug 的映射表缓存在 `globalThis`。

### 4.3 Callout 插件设计

`src/lib/remark-callout.ts`：

把 `> [!note]` / `> [!warning]` / `> [!tip]-`（折叠）转换成 `<aside class="callout callout-note">`。

```ts
const CALLOUT = /^\[!(\w+)\]([-+]?)\s*(.*)$/;

export function remarkCallout() {
  return (tree) => {
    visit(tree, 'blockquote', (node, index, parent) => {
      if (!node.children?.length) return;
      const first = node.children[0];
      if (first.type !== 'paragraph') return;
      const firstText = first.children?.[0];
      if (firstText?.type !== 'text') return;

      const m = firstText.value.match(CALLOUT);
      if (!m) return;

      const [, type, foldMark, titleText] = m;
      const folded = foldMark === '-';
      const defaultOpen = foldMark === '+';

      // 剥掉第一行的 [!xxx] 标记
      firstText.value = titleText;
      if (!titleText) first.children.shift();

      const calloutNode = {
        type: 'html',
        value: renderCalloutOpen(type, folded, defaultOpen, titleText),
      };
      const calloutClose = { type: 'html', value: renderCalloutClose(folded) };

      parent.children.splice(index, 1, calloutNode, ...node.children, calloutClose);
    });
  };
}
```

支持的类型（映射到 `Callout.astro` 的样式类）：

| Obsidian 类型 | CSS class | 图标 |
|---|---|---|
| `note` | `.callout-note` | ℹ️ |
| `tip` / `hint` | `.callout-tip` | 💡 |
| `info` | `.callout-info` | ℹ️ |
| `warning` / `attention` | `.callout-warning` | ⚠️ |
| `danger` / `error` | `.callout-danger` | 🚫 |
| `success` / `done` | `.callout-success` | ✅ |
| `question` / `help` | `.callout-question` | ❓ |
| `failure` / `missing` | `.callout-failure` | ❌ |
| `bug` | `.callout-bug` | 🐛 |
| `example` | `.callout-example` | 📝 |
| `quote` | `.callout-quote` | 💬 |
| `abstract` / `summary` | `.callout-abstract` | 📄 |

未识别类型 → 降级为 `.callout-note`。

### 4.4 Mermaid 插件设计

遇到 `` ```mermaid `` 代码块：
1. 保留 fenced code 的源文本
2. 输出一个占位 `<div data-mermaid>SOURCE</div>`
3. 在客户端 `MermaidIsland.tsx` 里 `client:visible` 懒加载 mermaid.js 渲染

避免把整个 mermaid.js（~1MB）打进首屏。

### 4.5 Dataview / Templater 剥离

`src/lib/remark-dataview-strip.ts`：直接从 AST 里删除满足以下条件的 code node：

- 语言是 `dataview` / `dataviewjs`
- 内容以 `<%*` 开头（Templater）
- Obsidian 注释 `%% ... %%`（要在 text 节点上做正则替换）

### 4.6 图片路径归一化（核心）

```
vault/SecNotes/40-Archive/HTB Machines/htb bruno.md
  └─ ![[image 1.png]]
```

构建时：

1. `src/lib/obsidian-parser.ts` 先扫一遍 vault，建立图片索引：
   ```ts
   Map<string /* 原名 "image 1.png" */, string /* 绝对路径 */>
   ```
2. `remark-wikilink` 把 `![[image 1.png]]` 转成 `<img src="image 1.png">`
3. `rehype-image-rewrite` 处理所有 `<img>`：
   - 查索引表拿到绝对路径
   - 规范化：`normalizeAssetName(name)` → `image-1.png`
     - 空格/下划线 → `-`
     - 中文 → `pinyin-<3位字符hash>`（保证唯一且 ASCII）
     - 转小写
   - 拷贝到 `dist/_images/<normalized>`（Astro 的 `public/` 是静态，我们用专属目录避免冲突）
   - 改写 `src="/_images/image-1.png"`
4. 若索引未命中：输出 `<span class="missing-image">⚠ Missing: image 1.png</span>`，构建日志 WARN

> 用 `/_images/` 而不是 `/images/` 是为了避免 vault 里可能存在的 `public/images/` 被误当成站点静态资源。

### 4.7 完整渲染顺序

```
Raw Markdown
  ↓ remarkDataviewStrip    (移除 dataview / templater / %%comments%%)
  ↓ remarkCallout          (> [!note] → aside)
  ↓ remarkWikilink         (![[img]] / [[link]])
  ↓ remarkMermaid          (```mermaid → island)
  ↓ remarkMath             ($$...$$)
  ↓                        ← Astro 内置 Shiki 高亮 ```lang 代码块
MDAST → HAST
  ↓ rehypeSlug             (给 h1-h6 加 id)
  ↓ rehypeAutolinkHeadings (标题变成可点击锚点)
  ↓ rehypeKatex            (数学公式)
  ↓ rehypeImageRewrite     (图片路径归一化 + 文件拷贝)
Final HTML
```

---

## 5. 页面结构与路由

### 5.1 BaseLayout

`src/layouts/BaseLayout.astro`：所有页面的外壳。

```astro
---
interface Props {
  title: string;
  description?: string;
  keywords?: string;
  ogType?: 'website' | 'article';
  ogImage?: string;
  canonical?: string;
  noindex?: boolean;
}
const {
  title,
  description = 'Xyvora - Web Security & CTF Notes',
  keywords = 'Xyvora, HTB, CTF, Web Security',
  ogType = 'website',
  ogImage,
  canonical = Astro.url.href,
  noindex = false,
} = Astro.props;

const GSC = import.meta.env.GOOGLE_SITE_VERIFICATION;
const CF_TOKEN = import.meta.env.PUBLIC_CF_ANALYTICS_TOKEN;
---

<!DOCTYPE html>
<html lang="zh-CN" data-theme="dark" data-lang="zh">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{title}</title>
    <meta name="description" content={description} />
    <meta name="keywords" content={keywords} />
    <link rel="canonical" href={canonical} />
    {noindex && <meta name="robots" content="noindex" />}

    <!-- OG -->
    <meta property="og:type" content={ogType} />
    <meta property="og:title" content={title} />
    <meta property="og:description" content={description} />
    {ogImage && <meta property="og:image" content={ogImage} />}
    <meta property="og:url" content={canonical} />
    <meta property="og:site_name" content="Xyvora" />

    <!-- Twitter -->
    <meta name="twitter:card" content="summary_large_image" />
    <meta name="twitter:title" content={title} />
    <meta name="twitter:description" content={description} />
    {ogImage && <meta name="twitter:image" content={ogImage} />}

    <!-- 搜索引擎验证 -->
    {GSC && <meta name="google-site-verification" content={GSC} />}

    <!-- 主题初始化（防闪烁）-->
    <script is:inline>
      (function () {
        const t = localStorage.getItem('theme') || 'dark';
        document.documentElement.setAttribute('data-theme', t);
        const l = localStorage.getItem('lang') ||
          (navigator.language.startsWith('zh') ? 'zh' : 'en');
        document.documentElement.setAttribute('data-lang', l);
        document.documentElement.setAttribute(
          'lang', l === 'en' ? 'en' : 'zh-CN'
        );
      })();
    </script>

    <!-- Cloudflare Web Analytics -->
    {CF_TOKEN && (
      <script
        defer
        src='https://static.cloudflareinsights.com/beacon.min.js'
        data-cf-beacon={`{"token": "${CF_TOKEN}"}`}
      />
    )}

    <link rel="stylesheet" href="/styles/global.css" />
  </head>
  <body>
    <Header />
    <main><slot /></main>
    <Footer />
  </body>
</html>
```

### 5.2 路由清单

| 文件 | 路径 | 说明 |
|---|---|---|
| `src/pages/index.astro` | `/` | 首页（Hero + 精选 + 最新） |
| `src/pages/post/[slug].astro` | `/post/<slug>/` | 文章详情 |
| `src/pages/about.astro` | `/about/` | 关于页 |
| `src/pages/archives.astro` | `/archives/` | 按年月归档 |
| `src/pages/tags/index.astro` | `/tags/` | 标签索引 |
| `src/pages/tags/[tag].astro` | `/tags/<name>/` | 单个标签的文章列表 |
| `src/pages/categories/index.astro` | `/categories/` | 分类索引 |
| `src/pages/categories/[name].astro` | `/categories/<name>/` | 单个分类列表 |
| `src/pages/404.astro` | `/404` | 404 页面 |
| `src/pages/sitemap-index.xml.ts` | `/sitemap-index.xml` | sitemap（插件生成） |
| `src/pages/rss.xml.ts` | `/rss.xml` | RSS |
| `public/robots.txt` | `/robots.txt` | 静态 robots |

### 5.3 首页（`src/pages/index.astro`）

```astro
---
import BaseLayout from '@/layouts/BaseLayout.astro';
import Hero from '@/components/Hero.astro';
import FeaturedPost from '@/components/FeaturedPost.astro';
import PostCard from '@/components/PostCard.astro';
import SearchModal from '@/components/SearchModal.astro';
import { getPublishedPosts } from '@/lib/obsidian-parser';

const allPosts = await getPublishedPosts();
const featured = allPosts[0];
const rest = allPosts.slice(1, 13); // 首页最多显示 12 篇
---

<BaseLayout title="Xyvora" description="Web Security & CTF Writeups">
  <Hero />
  <section class="max-w-6xl mx-auto px-6 -mt-10">
    <SearchModal posts={allPosts} />
  </section>

  {featured && <FeaturedPost post={featured} />}

  <section class="max-w-6xl mx-auto px-6 pb-24">
    <h2 class="text-2xl font-semibold mb-8 flex items-center gap-2">
      <span class="lang-zh">最新文章</span>
      <span class="lang-en">Latest</span>
    </h2>
    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
      {rest.map((p) => <PostCard post={p} />)}
    </div>
  </section>
</BaseLayout>
```

### 5.4 文章详情（`src/pages/post/[slug].astro`）

```astro
---
import { getCollection, render } from 'astro:content';
import PostLayout from '@/layouts/PostLayout.astro';
import LockedBanner from '@/components/LockedBanner.astro';
import { getPostWithTranslation } from '@/lib/obsidian-parser';

export async function getStaticPaths() {
  const { getPublishedPosts } = await import('@/lib/obsidian-parser');
  const posts = await getPublishedPosts();
  return posts.map((post) => ({
    params: { slug: post.data.Slug },
    props: { post },
  }));
}

const { post } = Astro.props;
const { en } = await getPostWithTranslation(post.data.Slug);

const locked = post.data['是否锁住'] === true;

const { Content: ContentZh } = await render(post);
const ContentEn = en ? (await render(en)).Content : null;
---

<PostLayout post={post} en={en}>
  <div class="lang-zh">
    {locked ? <LockedBanner /> : <ContentZh />}
  </div>
  <div class="lang-en">
    {locked
      ? <LockedBanner />
      : ContentEn
        ? <ContentEn />
        : <div class="alert">
            <span>This post has not been translated yet.</span>
          </div>
    }
  </div>
</PostLayout>
```

### 5.5 PostLayout

骨架（片段）：

```astro
---
import BaseLayout from '@/layouts/BaseLayout.astro';
import TableOfContents from '@/components/TableOfContents.astro';
import ReadingProgress from '@/components/ReadingProgress.astro';
import Giscus from '@/components/Giscus.astro';
import { calcReadingTime } from '@/lib/reading-time';

const { post, en } = Astro.props;
const { headings } = await render(post);
const readingTime = calcReadingTime(post.body);
---

<BaseLayout
  title={post.data.机器名称 || post.data.Slug}
  description={post.data.简介}
  ogType="article"
  keywords={post.data.tags?.join(', ')}
>
  <ReadingProgress />

  <article class="max-w-6xl mx-auto px-6 py-10 grid lg:grid-cols-[1fr_240px] gap-12">
    <div class="prose-wrap">
      <header>
        <h1>{post.data.机器名称}</h1>
        <!-- meta: 日期 / 阅读时长 / 类型 / 标签 / 语言切换 / 分享 -->
      </header>

      <div class="post-content">
        <slot />
      </div>

      <Giscus slug={post.data.Slug} />
    </div>

    <aside class="hidden lg:block">
      <TableOfContents headings={headings} />
    </aside>
  </article>
</BaseLayout>
```

---

## 6. 前端交互与样式

### 6.1 主题系统

用 CSS 自定义属性，根据 `<html data-theme="dark|light">` 切换。

`src/styles/theme.css`：

```css
:root[data-theme='dark'] {
  --bg:             #0a0a0a;
  --bg-elevated:    #111113;
  --bg-card:        #15171e;
  --border:         rgba(255, 255, 255, 0.08);
  --text:           #e5e7eb;
  --text-dim:       #9ca3af;
  --primary:        #10b981;  /* emerald-500 */
  --primary-soft:   rgba(16, 185, 129, 0.12);
  --code-bg:        #1a1d24;
}

:root[data-theme='light'] {
  --bg:             #ffffff;
  --bg-elevated:    #fafafa;
  --bg-card:        #f8fafc;
  --border:         rgba(0, 0, 0, 0.08);
  --text:           #1f2937;
  --text-dim:       #6b7280;
  --primary:        #059669;
  --primary-soft:   rgba(5, 150, 105, 0.08);
  --code-bg:        #f1f5f9;
}
```

所有组件通过 `var(--text)` 等引用，不在组件里写死颜色。

### 6.2 语言切换（单页 CSS）

`src/styles/global.css`：

```css
html[data-lang='zh'] .lang-en { display: none; }
html[data-lang='en'] .lang-zh { display: none; }
```

`LangToggle.astro`：

```astro
<button id="lang-toggle" class="...">
  <span class="lang-zh">EN</span>
  <span class="lang-en">中文</span>
</button>
<script>
  document.getElementById('lang-toggle')?.addEventListener('click', () => {
    const html = document.documentElement;
    const cur = html.getAttribute('data-lang');
    const next = cur === 'zh' ? 'en' : 'zh';
    html.setAttribute('data-lang', next);
    html.setAttribute('lang', next === 'en' ? 'en' : 'zh-CN');
    localStorage.setItem('lang', next);
  });
</script>
```

### 6.3 AI Cover

`src/components/AICover.astro`：

```astro
---
interface Props {
  title: string;
  category?: string;
}
const { title, category = 'default' } = Astro.props;
const toneMap = {
  HTB:    'from-emerald-500/20',
  方法论:  'from-sky-500/20',
  工具:    'from-violet-500/20',
  CTF:    'from-rose-500/20',
  default:'from-zinc-500/20',
};
const tone = toneMap[category] || toneMap.default;
---

<div class={`ai-cover h-48 rounded-2xl border relative overflow-hidden bg-[var(--bg-card)]`}>
  <div class={`absolute inset-0 bg-gradient-to-br ${tone} to-transparent`}></div>
  <div class="absolute inset-0 opacity-20 [background-image:linear-gradient(rgba(255,255,255,0.12)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.12)_1px,transparent_1px)] [background-size:22px_22px]"></div>
  <div class="absolute top-4 left-4 text-[10px] uppercase tracking-[0.3em] text-[var(--text-dim)]">
    {category}
  </div>
  <div class="absolute left-5 right-5 bottom-5">
    <h3 class="text-xl font-semibold leading-tight text-[var(--text)] line-clamp-3">
      {title}
    </h3>
  </div>
</div>
```

### 6.4 搜索（Ctrl+K / ⌘+K）

客户端实现，用 Fuse.js 做模糊搜索。

- 构建期把 `getPublishedPosts()` 的精简信息（slug / title / summary / tags / category）序列化到 `/search-index.json`
- `SearchModal.astro` 加载该 JSON，按需打开弹层
- 快捷键监听放到 BaseLayout 的内联脚本里

```ts
const fuse = new Fuse(data, {
  keys: ['title', 'summary', 'tags', 'category'],
  threshold: 0.3,
});
```

### 6.5 Prism vs Shiki

**选 Shiki**：Astro 内置、构建时高亮（零运行时 JS）、支持双主题（自动切换）、输出的 HTML 可直接复制。

原 Flask 项目里前端动态加的 Prism 代码块头（语言图标 + 复制按钮）要用一个轻量 JS 文件在 `post.html` 初始化：

`src/components/CodeBlockWrapper.astro` 包一层加语言标签 + 复制按钮，CSS 样式照搬 `base.css` 的 `code-block-wrapper` / `code-header` / `copy-code-btn` 部分。

### 6.6 Reading Progress / TOC / Back-to-top

- **ReadingProgress**：一条 fixed top 的 `<div>`，`window.scroll` 事件根据滚动百分比更新 `width`
- **TableOfContents**：从 Astro `render(post).headings` 取，按 depth 渲染缩进列表，IntersectionObserver 做"当前位置高亮"
- **Back-to-top**：滚动超过 400px 时 fade-in，点击 `scrollTo({top:0, behavior:'smooth'})`

---

## 7. 翻译脚本设计

### 7.1 入口 `scripts/translate.py`

```python
#!/usr/bin/env python3
"""Obsidian vault translation script (ZH → EN)."""

import argparse
import hashlib
import logging
import sys
from pathlib import Path
from lib.frontmatter import read_note, write_note
from lib.llm_client import LlmClient
from lib.hash_util import compute_source_hash

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--vault', type=Path, required=True,
                    help='path to vault root (e.g. ./vault or F:/Work/Obsidian)')
    ap.add_argument('--force', action='store_true', help='ignore cache')
    ap.add_argument('--only', type=str, help='only translate this slug')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
    log = logging.getLogger('translate')

    # 1. 扫描 vault 找所有 发布:true 的原文
    md_files = list(args.vault.rglob('*.md'))
    originals = [f for f in md_files if is_publishable_original(f)]
    log.info(f'Found {len(originals)} publishable originals')

    # 2. 过滤 --only
    if args.only:
        originals = [f for f in originals if get_slug(f) == args.only]

    client = LlmClient.from_env()
    stats = {'translated': 0, 'cached': 0, 'failed': 0, 'tokens': 0}

    for src in originals:
        en_path = src.with_suffix('.en.md')
        src_hash = compute_source_hash(src)

        if not args.force and en_path.exists():
            fm, _ = read_note(en_path)
            if fm.get('source_hash') == src_hash:
                log.info(f'  [CACHED] {src.relative_to(args.vault)}')
                stats['cached'] += 1
                continue

        log.info(f'  [TRANSLATE] {src.relative_to(args.vault)}')
        if args.dry_run:
            stats['translated'] += 1
            continue

        try:
            translated_fm, translated_body, tokens = translate_note(client, src, src_hash)
            write_note(en_path, translated_fm, translated_body)
            stats['translated'] += 1
            stats['tokens'] += tokens
        except Exception as e:
            log.error(f'  [FAIL] {src}: {e}')
            stats['failed'] += 1
            # 保留旧 en_path，不覆盖

    log.info(f'Summary: {stats}')
    # 写 GITHUB_STEP_SUMMARY 给 CI 用
    summary = Path(os.environ.get('GITHUB_STEP_SUMMARY', '/dev/null'))
    if summary.exists() or str(summary) == '/dev/null':
        with open(summary, 'a') as f:
            f.write(f'## Translation\n- translated: {stats["translated"]}\n'
                    f'- cached: {stats["cached"]}\n'
                    f'- failed: {stats["failed"]}\n'
                    f'- tokens: {stats["tokens"]}\n')

    sys.exit(0 if stats['failed'] == 0 else 1)

if __name__ == '__main__':
    main()
```

### 7.2 发布判定 `is_publishable_original`

```python
def is_publishable_original(path: Path) -> bool:
    if path.name.endswith('.en.md'):       # 译文本身
        return False
    if '/Templates/' in str(path):         # 模板文件
        return False
    fm, _ = read_note(path)
    return bool(fm.get('发布')) is True    # 严格比较
```

### 7.3 source_hash

```python
# lib/hash_util.py
import hashlib
from pathlib import Path
from .frontmatter import read_note

def compute_source_hash(path: Path) -> str:
    fm, body = read_note(path)
    # 从 fm 中剔除与翻译无关的易变字段（避免 Obsidian 每次保存时间戳变化导致全量重翻）
    keys_to_hash = [
        'Slug', '发布', '是否锁住', '日期', '类型',
        '难度', '操作系统', '简介', 'tags', '机器名称',
    ]
    hashable = {k: fm.get(k) for k in keys_to_hash}
    m = hashlib.sha256()
    m.update(repr(hashable).encode('utf-8'))
    m.update(b'\n---\n')
    m.update(body.encode('utf-8'))
    return m.hexdigest()
```

### 7.4 翻译核心逻辑

复用原 `sync_notion.py` 的思路：
- 把正文按 `^#+ ` 一级二级标题切块（避免整篇 > 12KB）
- 每块独立 LLM 调用，用 `<CONTENT>...</CONTENT>` 定界符
- 代码块 / 链接 / Wikilink / 行内 code 交给 LLM 的 system prompt 约束（见 §7.5）

```python
# lib/chunker.py
import re

HEADING_H2 = re.compile(r'^(#{1,2})\s', re.M)

def split_by_headings(body: str, max_chars: int = 10000) -> list[str]:
    if len(body) <= max_chars:
        return [body]
    parts = re.split(r'(?=^#{1,2}\s)', body, flags=re.M)
    chunks, cur = [], ''
    for p in parts:
        if len(cur) + len(p) <= max_chars:
            cur += p
        else:
            if cur:
                chunks.append(cur)
            cur = p
    if cur:
        chunks.append(cur)
    return chunks
```

### 7.5 System Prompt

```
You are an expert technical translator translating Chinese cybersecurity writeups to English.

HARD RULES (violating any rule = FAIL):
1. Preserve ALL Markdown structure: headings, lists, code blocks, blockquotes, tables.
2. Preserve ALL Obsidian syntax INTACT (no translation inside these):
   - ![[image.png]] / ![[image.png|300]]
   - [[note-name]] / [[note-name|alias]] / [[note#heading]]
   - %%...%% (just keep as-is)
3. Inside ``` fenced code blocks: preserve ALL code, variables, function names, CLI commands.
   ONLY inline comments (// # /* */) and natural-language string literals may be translated.
4. Keep inline code `...` as-is.
5. Preserve technical terms, CVE IDs, tool names (nmap, BurpSuite, Metasploit, etc.), file paths, URLs.
6. Preserve YAML frontmatter field names in Chinese (so downstream build can parse).
7. For frontmatter values (简介, 类型): translate values but keep keys unchanged.

You will receive the source between <SOURCE> tags.
Return the translation between <TRANSLATED> tags, nothing else.
```

### 7.6 frontmatter 组装

译文 frontmatter = 原文 frontmatter（除 `tags`）+ 翻译字段 + 翻译 meta。

```python
def build_translated_frontmatter(src_fm: dict, translated: dict, src_rel_path: str, src_hash: str) -> dict:
    out = dict(src_fm)  # copy all keys
    # 覆盖翻译字段
    if '简介' in translated:
        out['简介'] = translated['简介']
    if '类型' in translated:
        out['类型'] = translated['类型']
    if '机器名称' in translated:
        out['机器名称'] = translated['机器名称']
    # 追加 meta
    out['lang'] = 'en'
    out['source'] = src_rel_path
    out['source_hash'] = src_hash
    out['translated_at'] = datetime.utcnow().isoformat() + 'Z'
    # tags 不翻译，原样保留
    return out
```

---

## 8. GitHub Actions 工作流

### 8.1 site-repo `build.yml`

**职责：**
1. 收到 `repository_dispatch` 或 site-repo push 时触发
2. Clone vault → 翻译 → commit 回 vault
3. `npm run build`（Astro）
4. `rsync dist/` 到 VPS
5. SSH 执行 `docker compose up -d --no-deps --build neobee-blog` 重载容器

```yaml
name: Build and Deploy

on:
  push:
    branches: [main]
    paths-ignore:
      - '.kiro/**'
      - 'README.md'
  repository_dispatch:
    types: [vault-updated]
  workflow_dispatch:
    inputs:
      force_translate:
        type: boolean
        default: false
      skip_translate:
        type: boolean
        default: false

concurrency:
  group: build-deploy
  cancel-in-progress: false

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout site-repo
        uses: actions/checkout@v4

      - name: Setup SSH for vault-repo (clone)
        uses: webfactory/ssh-agent@v0.9.0
        with:
          ssh-private-key: ${{ secrets.VAULT_SSH_KEY }}

      - name: Clone vault-repo
        run: |
          git clone --depth 1 git@github.com:Neobee714/obsidian-vault.git vault
          cd vault
          echo "VAULT_SHA=$(git rev-parse HEAD)" >> $GITHUB_ENV

      - name: Setup Python
        if: ${{ !inputs.skip_translate }}
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: 'pip'
          cache-dependency-path: scripts/requirements.txt

      - name: Install Python deps
        if: ${{ !inputs.skip_translate }}
        run: pip install -r scripts/requirements.txt

      - name: Run translation
        if: ${{ !inputs.skip_translate }}
        env:
          LLM_API_KEY:  ${{ secrets.LLM_API_KEY }}
          LLM_BASE_URL: ${{ secrets.LLM_BASE_URL }}
          LLM_MODEL:    ${{ secrets.LLM_MODEL }}
        run: |
          ARGS="--vault ./vault"
          if [ "${{ inputs.force_translate }}" = "true" ]; then
            ARGS="$ARGS --force"
          fi
          python scripts/translate.py $ARGS

      - name: Commit translations back to vault-repo
        if: ${{ !inputs.skip_translate }}
        env:
          VAULT_PUSH_TOKEN: ${{ secrets.VAULT_PUSH_TOKEN }}
        run: |
          cd vault
          git config user.name  "xyvora-bot"
          git config user.email "bot@xyvora.local"
          git add -A
          if git diff --staged --quiet; then
            echo "No translation changes"
          else
            COUNT=$(git diff --staged --name-only | wc -l)
            git commit -m "chore(translate): update $COUNT files [skip ci]"
            git remote set-url origin \
              https://x-access-token:${VAULT_PUSH_TOKEN}@github.com/Neobee714/obsidian-vault.git
            git push
          fi

      - name: Setup Node
        uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'

      - name: Install Node deps
        run: npm ci

      - name: Build Astro
        env:
          ASTRO_VAULT_PATH:           ${{ github.workspace }}/vault
          PUBLIC_SITE_URL:            https://neobee.top
          PUBLIC_GISCUS_REPO:         Neobee714/Neobee714.github.io
          PUBLIC_GISCUS_REPO_ID:      ${{ secrets.PUBLIC_GISCUS_REPO_ID }}
          PUBLIC_GISCUS_CATEGORY:     ${{ secrets.PUBLIC_GISCUS_CATEGORY }}
          PUBLIC_GISCUS_CATEGORY_ID:  ${{ secrets.PUBLIC_GISCUS_CATEGORY_ID }}
          PUBLIC_CF_ANALYTICS_TOKEN:  ${{ secrets.PUBLIC_CF_ANALYTICS_TOKEN }}
          GOOGLE_SITE_VERIFICATION:   ${{ secrets.GOOGLE_SITE_VERIFICATION }}
        run: |
          npm run build
          echo "DIST_SIZE=$(du -sh dist | cut -f1)" >> $GITHUB_ENV
          echo "DIST_FILES=$(find dist -type f | wc -l)" >> $GITHUB_ENV

      - name: Setup SSH for VPS (deploy)
        uses: webfactory/ssh-agent@v0.9.0
        with:
          ssh-private-key: ${{ secrets.VPS_SSH_KEY }}

      - name: Add VPS to known_hosts
        run: |
          ssh-keyscan -H ${{ secrets.VPS_HOST }} >> ~/.ssh/known_hosts

      - name: Rsync dist/ to VPS (atomic)
        env:
          VPS_HOST: ${{ secrets.VPS_HOST }}
          VPS_USER: ${{ secrets.VPS_USER }}
          VPS_PATH: ${{ secrets.VPS_PATH }}
        run: |
          # 写到临时目录再 rename，避免半量文件被访问
          rsync -az --delete --stats \
            -e "ssh -o StrictHostKeyChecking=accept-new" \
            dist/ \
            ${VPS_USER}@${VPS_HOST}:${VPS_PATH}.new/

          ssh ${VPS_USER}@${VPS_HOST} "\
            rm -rf ${VPS_PATH}.old && \
            ([ -d ${VPS_PATH} ] && mv ${VPS_PATH} ${VPS_PATH}.old || true) && \
            mv ${VPS_PATH}.new ${VPS_PATH} && \
            echo 'Dist swapped successfully'"

      - name: Reload neobee-blog container
        env:
          VPS_HOST: ${{ secrets.VPS_HOST }}
          VPS_USER: ${{ secrets.VPS_USER }}
          VPS_COMPOSE_DIR: ${{ secrets.VPS_COMPOSE_DIR }}
        run: |
          ssh ${VPS_USER}@${VPS_HOST} "\
            cd ${VPS_COMPOSE_DIR} && \
            docker compose up -d --no-deps --build neobee-blog && \
            docker compose ps neobee-blog"

      - name: Smoke test
        run: |
          sleep 3
          curl -fsSL -o /dev/null -w "%{http_code}" https://neobee.top/ | grep -q '200' \
            || (echo "Homepage not 200" && exit 1)
          echo "Smoke test passed"

      - name: Summary
        run: |
          cat >> $GITHUB_STEP_SUMMARY << EOF
          ## Build & Deploy
          - Vault SHA: \`${VAULT_SHA}\`
          - Dist size: ${DIST_SIZE}
          - Dist files: ${DIST_FILES}
          - Deployed to: ${{ secrets.VPS_HOST }}
          EOF
```

### 8.2 关键点

- **原子切换**：rsync 先写 `dist.new/` → ssh 里 `mv dist → dist.old / mv dist.new → dist`，访问者不会看到半量文件
- `[skip ci]` 在翻译 commit 里防止 vault-repo 二次触发
- `ssh-keyscan` 首次运行会把 VPS 公钥添加到 known_hosts，避免交互确认
- Smoke test 用 HTTP 200 做快速验证，失败则整个 workflow 失败（但不回滚——VPS 上 `dist.old` 还在，手动可恢复）

### 8.3 vault-repo `notify.yml`

位置：`F:\Work\Obsidian\.github\workflows\notify.yml`

```yaml
name: Notify site-repo

on:
  push:
    branches: [main]
    paths:
      - 'SecNotes/**'
      - 'Templates/**'
    paths-ignore:
      - '**/*.en.md'
      - '**/.obsidian/**'

jobs:
  notify:
    runs-on: ubuntu-latest
    steps:
      - name: Dispatch event to site-repo
        run: |
          curl -fsSL -X POST \
            -H "Authorization: Bearer ${{ secrets.SITE_DISPATCH_TOKEN }}" \
            -H "Accept: application/vnd.github+json" \
            https://api.github.com/repos/Neobee714/Neobee714.github.io/dispatches \
            -d '{"event_type":"vault-updated","client_payload":{"sha":"${{ github.sha }}"}}'
```

> `paths-ignore: '**/*.en.md'` 防止翻译产物被 push 回去后再次触发无限循环。

### 8.4 （可选）VPS 侧部署脚本

如果启用 §1.5 的 `command=` 限制，需要在 VPS 建 `/root/neobee-stack/deploy-blog.sh`：

```bash
#!/bin/bash
# VPS 上限制 CI key 只能执行此脚本
# 根据 SSH_ORIGINAL_COMMAND 环境变量决定操作
set -e
case "$SSH_ORIGINAL_COMMAND" in
    rsync*)
        # 允许 rsync 到指定目录
        exec $SSH_ORIGINAL_COMMAND
        ;;
    *docker\ compose\ up*neobee-blog*)
        # 允许 docker compose 操作 neobee-blog
        cd /root/neobee-stack
        docker compose up -d --no-deps --build neobee-blog
        docker compose ps neobee-blog
        ;;
    *mv*dist*|*rm*dist.old*)
        exec $SSH_ORIGINAL_COMMAND
        ;;
    *)
        echo "Command not allowed: $SSH_ORIGINAL_COMMAND" >&2
        exit 1
        ;;
esac
```

此脚本为可选加固，**初次部署可以不启用**。

---

## 9. VPS 部署设计

### 9.1 整体方针

- 保持 `neobee-nginx`（对外反代 + SSL 终结）**不动**
- 保持 `bookkeeping-*` 相关容器**不动**
- **只改造 `neobee-blog`**：从 Flask + gunicorn 变成 Nginx + 静态文件
- 容器名保持 `neobee-blog`，内部监听端口从 `5000` 改为 `80`
- 相应地修改 `/root/neobee-stack/nginx.conf` 中对博客的 `proxy_pass` 目标端口

### 9.2 新 `neobee-blog` 容器设计

镜像方案：**直接用 `nginx:alpine`，不需要自定义 Dockerfile**。

`docker-compose.yml` 里 `neobee-blog` 服务定义调整为：

```yaml
  neobee-blog:
    image: nginx:alpine
    container_name: neobee-blog
    restart: unless-stopped
    volumes:
      - ./Neobee714.github.io/dist:/usr/share/nginx/html:ro
      - ./Neobee714.github.io/nginx-site.conf:/etc/nginx/conf.d/default.conf:ro
    expose:
      - "80"
```

**变化对比：**

| 项 | 旧 | 新 |
|---|---|---|
| `image` | `neobee-stack-neobee-blog`（自建 Flask 镜像） | `nginx:alpine` |
| `build` | `./Neobee714.github.io` | 移除 |
| `command` | `gunicorn app:app --bind 0.0.0.0:5000` | 移除（用 nginx 默认 CMD） |
| `expose` | `5000` | `80` |
| `volumes` | 无 | 挂载 `dist/` + 站点 nginx 配置 |
| `depends_on` | `redis` | 移除（不再需要 redis） |
| `environment` | 多个 Flask 环境变量 | 全部移除 |

`neobee-redis` 容器如果**只是**服务 Flask 博客，可以一并移除；如果 bookkeeping 也用到就保留。目前 compose 显示 bookkeeping-backend 并未 depends_on redis，可以移除。**保守起见先保留，后续确认无依赖再清理。**

### 9.3 `Neobee714.github.io/nginx-site.conf`（容器内站点配置）

新增文件 `/root/neobee-stack/Neobee714.github.io/nginx-site.conf`：

```nginx
server {
    listen 80;
    server_name _;

    root /usr/share/nginx/html;
    index index.html;

    # 静态资源长缓存（Astro 在文件名里加了 hash）
    location /_assets/ {
        expires 1y;
        add_header Cache-Control "public, immutable";
        try_files $uri =404;
    }
    location /_images/ {
        expires 30d;
        add_header Cache-Control "public";
        try_files $uri =404;
    }

    # HTML 本身不长缓存，避免内容更新不可见
    location ~* \.(html)$ {
        expires -1;
        add_header Cache-Control "no-cache, must-revalidate";
    }

    # Astro 的 trailing-slash 路由：/post/abc/ → /post/abc/index.html
    location / {
        try_files $uri $uri/ $uri/index.html =404;
    }

    # 自定义 404
    error_page 404 /404.html;

    # 禁止访问 hidden 文件
    location ~ /\. {
        deny all;
    }

    # gzip
    gzip on;
    gzip_vary on;
    gzip_min_length 256;
    gzip_types text/plain text/css text/xml application/json application/javascript application/xml+rss application/atom+xml image/svg+xml;
}
```

### 9.4 外层 `neobee-nginx` 反代配置调整

`/root/neobee-stack/nginx.conf` 中主站部分的 `proxy_pass` 改端口：

```diff
 server {
     listen 443 ssl;
     server_name neobee.top;

     ssl_certificate /etc/letsencrypt/live/neobee.top/fullchain.pem;
     ssl_certificate_key /etc/letsencrypt/live/neobee.top/privkey.pem;

     location / {
-        proxy_pass http://neobee-blog:5000;
+        proxy_pass http://neobee-blog:80;
         proxy_set_header Host $host;
         proxy_set_header X-Real-IP $remote_addr;
+        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
+        proxy_set_header X-Forwarded-Proto $scheme;
     }
 }
```

其他 `server` 块（API 等）完全不动。

### 9.5 VPS 初始化一次性操作

**已做：** Docker、docker-compose、`neobee-nginx`、Let's Encrypt 证书、bookkeeping 栈

**本次迁移要做（只需一次）：**

1. 清理旧 Flask 源码目录：
   ```bash
   cd /root/neobee-stack/Neobee714.github.io
   ls  # 记录哪些文件
   # 备份（可选）
   tar czf /root/neobee-blog-flask-backup.tar.gz .
   # 清空
   rm -rf ./*
   rm -rf .github .git .dockerignore   # 如果存在
   ```

2. 创建 dist 占位（避免 Nginx 启动时挂空目录报错）：
   ```bash
   mkdir -p /root/neobee-stack/Neobee714.github.io/dist
   echo '<h1>Placeholder</h1>' > /root/neobee-stack/Neobee714.github.io/dist/index.html
   ```

3. 写入 `nginx-site.conf`（§9.3 的内容）：
   ```bash
   vim /root/neobee-stack/Neobee714.github.io/nginx-site.conf
   ```

4. 更新 `docker-compose.yml` 中 `neobee-blog` 服务定义（§9.2）

5. 更新 `nginx.conf` 中 `proxy_pass` 端口（§9.4）

6. 重载：
   ```bash
   cd /root/neobee-stack
   docker compose up -d --no-deps neobee-blog
   docker compose restart neobee-nginx
   curl -I https://neobee.top/
   ```

   应该看到 `200 OK` 和 "Placeholder" 占位页。

7. 追加 CI 公钥到 `~/.ssh/authorized_keys`（见 §1.5）

### 9.6 Cloudflare DNS 配置

**当前状态**（从用户截图确认）：

- `neobee.top` A 记录 → `45.63.124.218`，Proxy status = **DNS only**（灰云）
- `www` A 记录同上
- 保持这个配置即可，不需要开橙云代理

Cloudflare Web Analytics 在 DNS only 模式下仍可工作，因为它基于站点内嵌的 script，不依赖代理。

### 9.7 自定义域名 & 证书续期

- **证书**：已由 `certbot` 容器管理，volume 挂载到 `./certbot/`。续期不受本次迁移影响。如果要验证续期 cron 是否存在，检查 VPS 的 `crontab -l` 或 `systemctl list-timers | grep cert`
- **www 跳转**：如果希望 `www.neobee.top` 也能访问（当前 DNS 已解析但 nginx.conf 里 `server_name` 不含 www），可以在主站 `server` 块加一个 301 跳转，**本次迁移可选**

### 9.8 回滚预案

失败时的恢复（来自 Actions 的部署步骤）：

```bash
ssh root@45.63.124.218
cd /root/neobee-stack/Neobee714.github.io
# dist.old 是上次部署的版本
mv dist dist.failed
mv dist.old dist
docker compose restart neobee-blog
```

再极端一点：从 legacy tag 恢复 Flask 版本（几乎不会需要）：

```bash
cd /root/neobee-stack/Neobee714.github.io
rm -rf ./*
git clone https://github.com/Neobee714/Neobee714.github.io.git .
git checkout legacy-flask-v1
# 恢复旧 docker-compose.yml（见 docker-compose.yml.bak）
cp /root/neobee-stack/docker-compose.yml.bak /root/neobee-stack/docker-compose.yml
docker compose up -d --build neobee-blog
```

---

## 10. robots.txt / sitemap / RSS

### 10.1 `public/robots.txt`

```
User-agent: *
Allow: /

Sitemap: https://neobee.top/sitemap-index.xml
```

### 10.2 sitemap 由 `@astrojs/sitemap` 自动生成

`astro.config.mjs` 里已挂载，构建后会产出：
- `/sitemap-index.xml`（总索引）
- `/sitemap-0.xml`（具体 URL）

### 10.3 RSS `src/pages/rss.xml.ts`

```ts
import rss from '@astrojs/rss';
import { getPublishedPosts } from '@/lib/obsidian-parser';

export async function GET(context) {
  const posts = await getPublishedPosts();
  return rss({
    title: 'Xyvora',
    description: 'Web Security & CTF Writeups',
    site: context.site,
    items: posts.slice(0, 20).map((p) => ({
      title: p.data.机器名称 ?? p.data.Slug,
      pubDate: p.data.日期,
      description: p.data.简介,
      link: `/post/${p.data.Slug}/`,
      categories: p.data.tags,
    })),
    customData: '<language>zh-CN</language>',
  });
}
```

---

## 11. Giscus 集成

`src/components/Giscus.astro`：

```astro
---
interface Props { slug: string }
const { slug } = Astro.props;
const repo      = import.meta.env.PUBLIC_GISCUS_REPO;
const repoId    = import.meta.env.PUBLIC_GISCUS_REPO_ID;
const category  = import.meta.env.PUBLIC_GISCUS_CATEGORY;
const categoryId= import.meta.env.PUBLIC_GISCUS_CATEGORY_ID;
---

{repo && repoId && (
  <div class="giscus-container mt-16 pt-10 border-t border-[var(--border)]"></div>
  <script is:inline define:vars={{ repo, repoId, category, categoryId }}>
    (function () {
      const s = document.createElement('script');
      s.src = 'https://giscus.app/client.js';
      s.setAttribute('data-repo', repo);
      s.setAttribute('data-repo-id', repoId);
      s.setAttribute('data-category', category);
      s.setAttribute('data-category-id', categoryId);
      s.setAttribute('data-mapping', 'pathname');
      s.setAttribute('data-theme',
        document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light');
      s.setAttribute('data-lang', 'zh-CN');
      s.crossOrigin = 'anonymous';
      s.async = true;
      document.querySelector('.giscus-container').appendChild(s);

      new MutationObserver(() => {
        const iframe = document.querySelector('iframe.giscus-frame');
        iframe?.contentWindow?.postMessage({
          giscus: { setConfig: {
            theme: document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light'
          }}
        }, 'https://giscus.app');
      }).observe(document.documentElement, {
        attributes: true, attributeFilter: ['data-theme']
      });
    })();
  </script>
)}
```

---

## 12. 性能预算校验

| 页面 | 首屏 JS（gzip） | LCP 目标 | 策略 |
|---|---|---|---|
| 首页 | ~30KB | ≤ 2s | Hero 动画用 Framer（scroll-triggered），SearchModal 打开时才加载 Fuse |
| 文章页 | ~80KB | ≤ 2.5s | Shiki 零运行时；Mermaid 用 `client:visible` 岛屿；TOC / 进度条用原生 JS |
| 文章页（带 KaTeX） | ~140KB | ≤ 2.5s | KaTeX 仅对含 `$` 的文章加载（在 rehype 阶段检测） |

---

## 13. 风险与开放项

| 风险 | 缓解 |
|---|---|
| vault push 频繁触发 CI 耗费 Action 分钟 | `paths` filter 只关注 `SecNotes/**`；单 push 翻译增量，总耗时 < 5min |
| 翻译脚本意外 commit 回 vault 引起循环触发 | vault-repo `notify.yml` 的 `paths-ignore: '**/*.en.md'` + 翻译 commit 带 `[skip ci]` 双保险 |
| LLM 输出有小概率漏内容 | 失败 fallback 不覆盖旧译文；log 里保留原始响应前后 100 字符 |
| 私仓 deploy key 泄露 | 只读 key，即使泄露也只能读不能写；定期轮换 |
| `.en.md` 被 Obsidian 双链误索引 | 在 Obsidian 里把 `*.en.md` 加入 Ignore 模式；或用 `_` 前缀重命名为 `htb bruno_.en.md`（可在 §10 讨论） |
| Mermaid 运行时 JS 膨胀 | 只在 `client:visible` 懒加载；对无 mermaid 的文章完全不加载 |
| VPS 部署失败导致站点挂掉 | rsync 使用 `dist.new → dist` 原子切换；旧 dist 保留为 `dist.old`，回滚一条命令 |
| CI SSH key 泄露 | 专用 ed25519 key，仅用于部署；可选 `command=` 限制只能执行部署脚本（§8.4） |
| Docker 镜像拉取失败 | VPS 已经在用 `nginx:alpine`，不涉及新镜像 |
| `neobee-nginx` 配置改错导致全站挂（含 bookkeeping） | 先本地 `nginx -t` 验证；只改一个 `proxy_pass` 端口，改动最小 |
| VPS 磁盘写满 | rsync 使用 `--delete` 不累积文件；`dist.old` 每次部署会被清理 |

---

## 14. 未尽事项（等 tasks.md）

- Obsidian 的 `*.en.md` 是否要改名更隐蔽（`.i18n/` 子目录？）—— 当前方案足够，除非 Obsidian 搜索体验被污染
- 访问量徽章（"👁 1234"）：如果后续想显示，用 CountAPI + Workers KV 加一个独立数据源
- Vault-repo 里的非笔记文件（`.obsidian/workspace.json` 等）已 gitignore，但个别插件目录可能还需要增补
- CI key 的 `command=` 加固（§8.4）**初次部署不启用**，上线稳定后再加
- www 子域名 301 跳转（§9.7）**初次部署不加**，有需要再补
