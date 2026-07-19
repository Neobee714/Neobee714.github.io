---
inclusion: always
---

# Xyvora 项目上下文

## 1. 项目概况

Xyvora 是一个由 Astro 生成的中文静态博客。站点代码位于公开的 `Neobee714/Neobee714.github.io` 仓库，文章位于私有的 `Neobee714/obsidian-vault` 仓库。vault 不作为 submodule 加入站点仓库。

`.kiro/specs/obsidian-blog-migration/` 保存的是迁移时期的归档规范。当前实现、测试、README 和工作流是现行行为的依据。

## 2. 技术栈

| 层 | 选型 |
|---|---|
| 静态站点生成 | Astro 6 |
| 样式 | Tailwind CSS + 自定义 CSS 变量 |
| 代码高亮 | Shiki |
| 公式 | KaTeX |
| 图表 | Mermaid |
| 评论 | Giscus |
| 访问统计 | Cloudflare Web Analytics |
| CI | GitHub Actions |
| 部署 | rsync 到 VPS + Nginx 容器 |

## 3. 内容与发布规则

- 站点只构建中文原文。
- 笔记可以位于 vault 的任意目录，目录不决定是否发布。
- `发布` 必须为 `true`、`yes` 或 `是`。
- `Slug` 必须存在且有效；重复 Slug 会使构建失败。
- `状态` 为 `进行中`、`draft`、`wip` 或 `writing` 时视为草稿，不发布。
- `是否锁住: Yes` 或 `状态: 已锁住` 的文章保留列表、RSS 和 sitemap 入口，但详情页隐藏正文。
- 文章 URL 为 `https://xyvora.me/post/<Slug>/`。

## 4. 构建与部署数据流

```text
Obsidian vault -> push -> repository_dispatch -> site Actions clone vault
  -> validate published Chinese posts -> Astro build -> rsync dist -> VPS Nginx
```

Actions 使用 `VAULT_SSH_KEY` 只读 clone vault，在 runner 上执行 Astro 构建，再使用 VPS SSH 凭据同步 `dist/`。随后重载 `neobee-blog` 容器并对 `https://xyvora.me/` 执行 smoke test。VPS 不执行站点构建。

## 5. 本地开发

- 需要 Node.js 22 或更高版本。
- 在被 gitignore 的 `.env` 中设置 `ASTRO_VAULT_PATH`，指向本地 Obsidian vault。
- 使用 `npm run dev` 启动开发服务器。
- 使用 `npm test` 运行 Node 测试，使用 `npm run build` 验证生产构建。

## 6. 凭据边界

- `.env` 永远不能提交，也不能在日志或对话中回显值。
- CI 从 GitHub Actions Secrets 读取 `VAULT_SSH_KEY`、VPS 部署凭据、站点验证与公开集成配置。
- vault 仓库使用 `SITE_DISPATCH_TOKEN` 通知站点仓库。
- 不使用个人默认 SSH key；vault clone 和 VPS 部署使用各自的专用 key。

## 7. 工作边界

- 本仓库的代码、测试、文档和工作流可按任务修改。
- 不直接修改私有 vault、VPS 容器、反向代理或其他服务，除非用户明确授权。
- 不修改 `.kiro/specs/obsidian-blog-migration/` 下的归档规范。
- force push、删除生产容器或修改 VPS 网络配置前必须获得明确确认。
