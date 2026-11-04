# DawnCMS

DawnCMS 独立博客系统（FastHTML + SQLite），可直接部署为任何网站的博客子站。

## 功能

- **前台**：文章列表（精选 + 分页）、分类页、文章详情（自动 TOC / 上一篇下一篇 / 相关文章推荐 / 外链新窗口 / 代码复制按钮）、站内搜索（owenboker 主题带 ⌘K 快速搜索弹窗，实时联想，多语言站搜对应译文）、`sitemap.xml`、`robots.txt`、JSON-LD（Article / BreadcrumbList / ItemList）
- **后台**（`/dadmin`，密码登录，前台无入口需手动输地址，旧 `/admin` 已 404）：文章 CRUD + Markdown 编辑器（实时预览 / slug 生成 / 历史版本恢复 / 发布下架）、分类管理、媒体库（上传自动转 WebP + 缩略图 / 引用统计）
- **SEO**：URL 结构 `/blog/{分类slug}/{文章slug}`、slug 变更自动 301 重定向（`post_slug_redirects`）、canonical、OG/Twitter meta
- **自动本地化**：正文中粘贴的远程图片 URL 在保存时自动下载并转 WebP 存到本地

## 快速开始

**一键安装（推荐）**：克隆后运行安装脚本，自动建 venv、装依赖、生成带随机密码的 `.env`——

```bash
git clone git@github.com:duoduoshopify/dawncms.git && cd dawncms

# Linux / macOS
bash install.sh && ./start.sh

# Windows：双击 install.bat 安装，然后双击 start.bat 启动
```

唯一前置要求：Python 3.10+（推荐 3.12，Windows 安装时勾选 "Add python.exe to PATH"）。

**手动安装**：

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # 修改站点名、域名、管理密码、SESSION_SECRET
python dawn_main.py    # 默认端口 5010
```

- 前台：http://localhost:5010/
- 后台：http://localhost:5010/dadmin （密码为 `.env` 的 `BLOG_ADMIN_PASSWORD`）

详细使用说明见 [使用说明.md](使用说明.md)。

## 运行环境

当前生产环境（与 `requirements.txt` 锁定一致）：

- **操作系统**：Ubuntu 24.04.4 LTS（x86_64）
- **Python**：3.12.3（Ubuntu 24.04 系统自带 `python3`），虚拟环境位于 `venv/`
- **Web 框架**：FastHTML 0.14.18（Starlette 1.10.0 + Uvicorn 0.54.0）
- **数据库**：SQLite（`aiosqlite` 0.22.1 异步驱动）
- **主要依赖**：Markdown 3.11.2、Pillow 13.0.0、aiohttp 3.14.5、Jinja2 3.1.6、python-dotenv 1.2.4、httpx2 2.16.0（python-fasthtml 依赖）

完整依赖及精确版本见 `requirements.txt`（由生产环境 `pip freeze` 导出，可直接复现整套环境）。

## 配置项（.env）

| 变量 | 说明 |
|------|------|
| SITE_NAME | 站点名称（导航/footer/标题后缀） |
| SITE_BASE_URL | 线上域名，用于 canonical / sitemap / 远程图判定 |
| BLOG_ADMIN_PASSWORD | 后台登录密码 |
| SESSION_SECRET | 会话签名密钥，务必修改 |
| BLOG_DEFAULT_AUTHOR | 默认作者名 |
| PORT | 监听端口 |

## 目录结构

```
blog/          数据层（factory/models/crud，SQLite: database/blog.db）
services/      blog_service / markdown_renderer / blog_image_service / member / email
routes/        frontend.py（前台） / admin.py（后台）
ui/            layout.py（站点布局） / blog_pages.py / blog_article.py
static/uploads/blog/   媒体文件（按 年/月/日 分目录）
database/blog.db       SQLite 数据库（首次启动自动建表）
```

## Markdown 扩展语法

```
:::cta
title: 立即咨询
desc: 描述文案
button_text: 查看详情
button_url: /contact
:::

:::embed youtube https://www.youtube.com/watch?v=xxx :::
:::embed video /uploads/blog/xxx.mp4 :::
```

## 部署建议

- 生产环境用 uvicorn 反代（Nginx → 5010），并把 `static/` 交给 Nginx 直接服务
- `database/blog.db` 与 `static/uploads/` 需要纳入备份
- 完全独立的单体项目，无外部代码依赖
