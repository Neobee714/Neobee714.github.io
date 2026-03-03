# 图片下载功能说明

## 📸 两种图片处理模式

### 模式 1：使用 Notion CDN（默认，推荐）

**特点：**
- ✅ 同步速度快（不下载图片）
- ✅ 不占用服务器存储
- ✅ Notion CDN 速度快
- ⚠️ 依赖 Notion 图片服务
- ⚠️ 图片 URL 可能过期（通常 1 小时）

**使用方法：**
```bash
# 默认模式，无需配置
python sync_notion.py
```

---

### 模式 2：下载图片到本地（可选）

**特点：**
- ✅ 完全独立于 Notion
- ✅ 图片永久有效
- ✅ 加载速度更快（本地文件）
- ❌ 同步时间更长
- ❌ 占用服务器存储空间

**使用方法：**

#### 本地开发
```bash
# 设置环境变量启用图片下载
export DOWNLOAD_IMAGES=true  # Linux/Mac
set DOWNLOAD_IMAGES=true     # Windows

# 运行同步
python sync_notion.py
```

#### Railway 部署
在 Railway 环境变量中添加：
```
DOWNLOAD_IMAGES=true
```

然后重新部署。

---

## 🔧 工作原理

### 图片下载流程

```
同步文章
    ↓
检测到图片 URL
    ↓
生成文件名（URL hash + 扩展名）
    ↓
下载图片到 blog-data/images/
    ↓
替换 JSON 中的 URL 为本地路径
    ↓
Flask 通过 /static/images/ 提供图片
```

### 文件命名规则

图片文件名使用 URL 的 MD5 hash：
```
原 URL: https://notion.so/image/abc123.jpg
文件名: 5d41402abc4b2a76b9719d911017c592.jpg
本地路径: /static/images/5d41402abc4b2a76b9719d911017c592.jpg
```

---

## 📊 性能对比

| 指标 | Notion CDN | 本地下载 |
|------|-----------|---------|
| 同步时间（47篇文章） | 2-3 分钟 | 5-10 分钟 |
| 存储占用 | 0 MB | 50-200 MB |
| 图片加载速度 | 快 | 极快 |
| 依赖性 | 依赖 Notion | 完全独立 |
| URL 有效期 | 1 小时 | 永久 |

---

## 🎯 推荐使用场景

### 使用 Notion CDN（默认）
- ✅ 快速部署和测试
- ✅ 存储空间有限
- ✅ 文章更新频繁
- ✅ 图片数量不多

### 下载到本地
- ✅ 需要完全独立于 Notion
- ✅ 图片需要永久有效
- ✅ 有充足的存储空间
- ✅ 追求极致加载速度

---

## 🐛 故障排查

### 问题 1：图片下载失败

**症状：** 日志显示 "下载图片失败"

**原因：**
- 网络连接问题
- Notion 图片 URL 已过期
- 磁盘空间不足

**解决方案：**
1. 检查网络连接
2. 重新运行同步脚本
3. 检查磁盘空间

### 问题 2：图片无法显示

**症状：** 网页上图片显示 404

**原因：**
- 图片文件不存在
- Flask 静态文件路由配置错误

**解决方案：**
1. 检查 `blog-data/images/` 目录是否有文件
2. 确认 Flask 路由 `/static/images/` 正常工作
3. 查看浏览器控制台错误信息

### 问题 3：Railway 部署后图片丢失

**症状：** 重启后图片无法访问

**原因：** Railway 文件系统是临时的

**解决方案：**
- 使用 Notion CDN 模式（推荐）
- 或使用外部对象存储（S3/OSS）

---

## 💡 最佳实践

### 本地开发
```bash
# 启用图片下载，方便离线开发
export DOWNLOAD_IMAGES=true
python sync_notion.py
python app.py
```

### Railway 部署
```bash
# 使用 Notion CDN，减少启动时间
# 不设置 DOWNLOAD_IMAGES 环境变量
```

### 生产环境（自有服务器）
```bash
# 启用图片下载，完全独立
export DOWNLOAD_IMAGES=true
python sync_notion.py

# 定期同步（crontab）
0 */6 * * * cd /path/to/blog && python sync_notion.py
```

---

## 📝 技术细节

### 图片下载实现

```python
def download_image(url, images_dir):
    """下载图片到本地"""
    # 1. 生成唯一文件名
    url_hash = hashlib.md5(url.encode()).hexdigest()
    ext = os.path.splitext(urlparse(url).path)[1] or '.jpg'
    filename = f"{url_hash}{ext}"

    # 2. 检查是否已存在
    if filepath.exists():
        return f"/static/images/{filename}"

    # 3. 下载图片
    response = requests.get(url, timeout=30, stream=True)
    with open(filepath, 'wb') as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)

    # 4. 返回本地路径
    return f"/static/images/{filename}"
```

### Flask 静态文件服务

```python
@app.route('/static/images/<path:filename>')
def serve_image(filename):
    """提供本地下载的图片"""
    images_dir = os.path.join(os.path.dirname(__file__), 'blog-data', 'images')
    return send_from_directory(images_dir, filename)
```

---

## 🔄 切换模式

### 从 CDN 切换到本地下载

```bash
# 1. 启用图片下载
export DOWNLOAD_IMAGES=true

# 2. 重新同步
python sync_notion.py

# 3. 重启应用
python app.py
```

### 从本地下载切换到 CDN

```bash
# 1. 禁用图片下载
export DOWNLOAD_IMAGES=false

# 2. 重新同步
python sync_notion.py

# 3. 可选：删除本地图片
rm -rf blog-data/images/*

# 4. 重启应用
python app.py
```

---

## 总结

- **默认使用 Notion CDN**：快速、简单、适合大多数场景
- **需要时启用本地下载**：完全独立、永久有效、极致性能
- **Railway 部署推荐 CDN**：避免文件系统临时性问题
- **自有服务器推荐本地**：充分利用服务器资源
