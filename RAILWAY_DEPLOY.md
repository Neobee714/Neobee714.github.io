# Railway 部署指南

## 📦 部署步骤

### 1. 准备工作

确保你的项目已经推送到 Git 仓库（GitHub/GitLab/Bitbucket）。

### 2. 在 Railway 创建项目

1. 访问 [railway.app](https://railway.app)
2. 点击 "New Project"
3. 选择 "Deploy from GitHub repo"
4. 选择你的博客仓库

### 3. 配置环境变量

在 Railway 项目设置中添加以下环境变量：

**必需变量：**
```
NOTION_TOKEN=your_notion_integration_token
NOTION_DATABASE_ID=your_database_id
SECRET_KEY=your_secret_key_here
```

**可选变量：**
```
FLASK_DEBUG=false
ADMIN_PASSWORD=your_admin_password
GISCUS_REPO=your_repo
GISCUS_REPO_ID=your_repo_id
GISCUS_CATEGORY=your_category
GISCUS_CATEGORY_ID=your_category_id
LLM_API_KEY=your_llm_api_key
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini
```

### 4. 部署配置

Railway 会自动检测到以下文件：
- `Procfile` - 定义启动命令
- `railway.json` - Railway 配置
- `requirements.txt` - Python 依赖
- `start.sh` - 启动脚本

### 5. 部署流程

Railway 会自动执行以下步骤：

```
1. 安装依赖 (pip install -r requirements.txt)
2. 运行启动脚本 (bash start.sh)
   ├─ 同步 Notion 数据到本地
   └─ 启动 Gunicorn 服务器
```

### 6. 查看部署日志

在 Railway 控制台的 "Deployments" 标签页可以看到：
```
==========================================
Railway 启动流程
==========================================
步骤 1: 同步 Notion 数据...
找到 47 篇文章
[1/47] 同步文章: ezAI2 (ezAI2)
...
✓ 数据同步成功

步骤 2: 启动 Web 服务器...
==========================================
[INFO] Starting gunicorn 21.2.0
[INFO] Listening at: http://0.0.0.0:8080
```

## 🔄 更新内容

### 方式 1：重新部署（推荐）

在 Railway 控制台点击 "Redeploy" 按钮，会：
1. 重新同步 Notion 数据
2. 重启应用

### 方式 2：手动同步

访问后台管理页面 `/admin/sync`，点击"同步"按钮。

**注意**：Railway 的文件系统是临时的，手动同步的数据在重启后会丢失。

## ⚙️ 工作原理

### Railway 环境特点

- **临时文件系统**：每次重启会清空
- **无持久化存储**：不适合存储长期数据
- **启动时同步**：每次部署/重启时从 Notion 获取最新数据

### 数据流程

```
Railway 启动
    ↓
运行 start.sh
    ↓
执行 sync_notion.py
    ↓
从 Notion API 下载所有文章
    ↓
保存到 blog-data/ 目录（临时）
    ↓
启动 Flask 应用
    ↓
应用从本地文件读取数据（极快）
    ↓
重启时重复上述流程
```

### 性能优势

- **首次加载慢**：启动时需要同步数据（约 1-2 分钟）
- **运行时极快**：所有请求都从本地文件读取（毫秒级）
- **无 API 限制**：运行时不调用 Notion API

## 🐛 故障排查

### 问题 1：启动失败

**症状**：部署失败，日志显示 "数据同步失败"

**解决方案**：
1. 检查环境变量 `NOTION_TOKEN` 和 `NOTION_DATABASE_ID` 是否正确
2. 确认 Notion Integration 有数据库访问权限
3. 查看详细错误日志

### 问题 2：启动时间过长

**症状**：部署超过 5 分钟

**原因**：文章数量多，同步时间长

**解决方案**：
- 正常现象，等待同步完成
- 可以在 `start.sh` 中添加超时处理

### 问题 3：数据不更新

**症状**：在 Notion 修改文章后，网站没有更新

**解决方案**：
- Railway 控制台点击 "Redeploy" 重新部署
- 或访问 `/admin/sync` 手动同步（重启后会丢失）

## 📊 监控建议

### 启动时间监控

在 Railway 日志中查看：
```
步骤 1: 同步 Notion 数据...
找到 47 篇文章
同步完成！
  总文章数: 47
  分类数: 6
  标签数: 57
```

### 性能监控

- **首次部署**：1-2 分钟（同步数据）
- **后续请求**：< 100ms（本地文件）
- **内存占用**：约 150-200MB

## 🔧 高级配置

### 调整同步超时

编辑 `start.sh`：
```bash
# 添加超时限制（5 分钟）
timeout 300 python sync_notion.py || echo "同步超时，使用 API 后备"
```

### 禁用启动时同步

如果你想完全使用 Notion API（不推荐）：

编辑 `start.sh`，注释掉同步步骤：
```bash
# echo "步骤 1: 同步 Notion 数据..."
# python sync_notion.py
```

### 自定义启动命令

编辑 `Procfile`：
```
web: gunicorn --bind 0.0.0.0:$PORT --workers 4 --threads 2 app:app
```

## 💡 最佳实践

1. **定期重新部署**：每天或每周重新部署一次，确保数据最新
2. **监控日志**：关注同步是否成功
3. **备份环境变量**：保存一份环境变量配置
4. **测试部署**：修改代码后先在本地测试

## 📝 与本地开发的区别

| 特性 | 本地开发 | Railway 部署 |
|------|---------|-------------|
| 数据同步 | 手动或定时 | 启动时自动 |
| 文件持久化 | 永久保存 | 临时（重启丢失） |
| 定时任务 | 启用 | 禁用 |
| 数据更新 | 定时/手动 | 重新部署 |

## 🎯 总结

Railway 部署使用"启动时同步"策略：
- ✅ 每次部署获取最新数据
- ✅ 运行时性能极佳
- ✅ 配置简单，无需额外服务
- ⚠️ 启动时间稍长（1-2 分钟）
- ⚠️ 需要重新部署才能更新内容

这是 Railway 环境下的最佳方案！
