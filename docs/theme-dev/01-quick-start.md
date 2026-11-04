# 快速上手：10 分钟做一个主题包

拾墨博客（DawnCMS）的主题是 **Ghost 式主题包**：一个文件夹（或 zip），包含元信息、配色变量、静态资产、多语言文案和 Jinja2 模板。改配色可以只带两三个文件，改结构就带上自己的模板。

## 主题包结构（与内置主题一致）

以内置主题 shimo 为参照，完整结构如下（除 `theme.json` 外全部可选）：

```
my-theme/
├── theme.json          # 必填：元信息
├── vars.json           # 可选：CSS 变量覆盖（28 个 token）
├── style.css           # 可选：根目录附加 CSS（向后兼容旧包）
├── assets/
│   ├── core/           # 可选：平台基线（base.css / doc.css / doc.js / list.css）
│   │                   #       放同名文件即覆盖基线
│   ├── css/            # 可选：主题主样式，多个 .css 按文件名排序拼接（如 main.css）
│   ├── js/             # 可选：主题脚本，多个 .js 按文件名排序拼接（如 theme.js）
│   ├── fonts/          # 可选：字体文件（woff2 等）
│   └── img/            # 可选：图片（logo.svg 等）
├── locales/            # 可选：前台 UI 文案翻译（{lang}.json，见下文「多语言」）
└── templates/          # 可选：Jinja2 模板（无 extends 时 base.html 必填）
    ├── base.html
    ├── list.html       # 首页/分类/标签/搜索共用
    ├── post.html       # 文章页
    ├── gate.html       # 会员门禁页
    ├── page.html       # 通用页面（关于等）
    ├── 404.html        # 错误页（404 与 500 共用，可选；缺省时回退默认主题的同名模板）
    └── partials/       # nav.html / footer.html / post_card.html
```

## 加载与合并规则

继承链为「子主题 → 父主题（extends）→ 默认值」，不同资产合并方式不同：

| 资产 | 合并方式 |
|---|---|
| `vars.json` | 默认值 → 父 → 子，逐 token 覆盖（key 里的连字符自动转下划线） |
| `style.css` + `assets/css/*.css` | **沿链拼接**：父主题在前、子主题在后（后者可覆盖前者）；css 目录内按文件名排序 |
| `assets/js/*.js` | 同 CSS：沿链拼接、按文件名排序，注入为 `theme_js` |
| `templates/` | 沿链查找，**子主题优先**（Jinja2 FileSystemLoader 按目录顺序命中） |
| `assets/core/*` | 平台基线文件（doc 样式/脚本等），沿链找同名文件，子主题优先 |
| `assets/` 静态文件 | 经 `/theme-assets/{key}/{path}` 对外服务（沿链查找、MIME 白名单、缓存 1 天） |
| `locales/*.json` | 沿链合并（父先子后，子覆盖同名 key） |

## 多语言（locales/）

前台 UI 文案（导航、按钮等）通过模板里的 `t("key", "默认值")` 输出，翻译表来自主题 `locales/` 目录：

- 文件名按 BCP 47：`en.json`、`zh-TW.json`、`ja.json`……
- **中文默认版特殊命名为 `zh-CN.default.json`**（它是兜底表，不是"翻译"）
- 回退链：`en-us` → `[en-us, en-US, en]`，逐级查找
- 无 `locales/` 目录的第三方主题自动兼容——i18n 插件经 `dawn_register_locale_provider` 注册兜底表

## 主题系统的三个来源

| 来源 | 位置 | 说明 |
|---|---|---|
| 内置主题 | `themes/{key}/` 目录 | 随代码分发：shimo（宣纸）/ baiye（白页）/ noir / mori / classic / sudo / owenboker（欧文博客·靛青，仿 Ghost Doks） |
| 上传主题包 | 后台「外观」上传 zip | 解压到 `themes/custom/{key}/` |
| 当前主题 | `site_settings` 表 | 后台点卡片即切换，无需重启 |

## 最小主题：只改配色

利用 `extends` 继承另一个主题的全部模板/资产/文案，自己只覆盖变量：

**theme.json**

```json
{
  "key": "sakura",
  "name": "樱花抄",
  "description": "樱粉底 · 绯红点缀",
  "author": "you",
  "version": "1.0",
  "extends": "shimo",
  "preview": ["#fdf2f4", "#3d2c31", "#d16b86"]
}
```

**vars.json**（只写要覆盖的 token，其余继承默认）

```json
{
  "paper": "#fdf2f4",
  "accent": "#d16b86",
  "accent_rgb": "209,107,134"
}
```

打成 zip 上传即可。完整示例：`examples/theme-sakura.zip`。

- `key`：唯一标识，2-32 位小写字母/数字/连字符（正则 `^[a-z0-9][a-z0-9-]{1,31}$`）
- `extends`：父主题 key。模板/变量/CSS/JS/locales/assets 全部沿继承链回退（子 → 父 → 默认值）
- 不写 `extends` 时，**必须自带 `templates/base.html`**，否则校验失败

## 完整主题：自带模板

把 `themes/shimo/templates/` 整套复制过来改。模板语法是 Jinja2，渲染在**沙盒环境**中执行（禁止属性穿越等危险操作），可用变量见各模板顶部注释。

`dawn_render()` 会为每个模板自动注入以下上下文（无需路由显式传）：

| 变量 | 内容 |
|---|---|
| `theme_key` | 当前主题 key |
| `t` | 翻译函数 `t("key", "默认值")`，查 `locales/` 与插件兜底表 |
| `theme_js` | `assets/js/*.js` 沿继承链拼接后的脚本文本 |
| `logo_url` | `assets/img/logo.svg` 的 `/theme-assets/` URL（找不到回退 `/static/logo.svg`） |

此外 `routes/dawn_frontend.py` 的 `_dawn_ctx()` 注入站点级变量（`site_name`/`page_title`/`canonical`/`site_schema`/`og_image`/`og_locale` 等）。

### base.html 的 head 插槽契约（SEO/GEO 插件依赖）

第三方主题的 `base.html` 必须保留以下插槽，否则 SEO/GEO 插件与多语言功能会静默失效（不报错，只是不输出）：

```html
{% if canonical %}<link rel="canonical" href="{{ canonical }}">{% endif %}
<meta property="og:locale" content="{{ og_locale or 'zh_CN' }}">
{% for ol in og_locale_alternates or [] %}<meta property="og:locale:alternate" content="{{ ol }}">{% endfor %}
<meta property="og:image" content="{{ og_image or (site_base_url + '/static/logo.svg') }}">
{% if robots_meta %}<meta name="robots" content="{{ robots_meta }}">{% endif %}
{% if extra_head %}{{ extra_head|safe }}{% endif %}
{% if site_schema %}{{ site_schema|safe }}{% endif %}
```

| 插槽 | 来源 | 作用 |
|---|---|---|
| `canonical` | 核心各页面路由 | 自引用 canonical；i18n 译文页指向译文 URL |
| `og_locale` / `og_locale_alternates` | 核心 `_dawn_ctx` / i18n 插件 | OG 区域标记（`zh_CN` ↔ `en_US`） |
| `og_image` | 核心默认 logo，seogeo 插件可改 | 社交分享图 |
| `robots_meta` | 核心（搜索/认证页 noindex）+ 文章路由 | robots 指令 |
| `extra_head` | 核心（文章 JSON-LD）+ `head_extra` 钩子 | seogeo/i18n 插件注入 hreflang、验证 meta 等 |
| `site_schema` | 核心 `_dawn_ctx`，seogeo 插件可重建 | 站点级 Organization/WebSite JSON-LD |

注意：`extra_head` 和 `site_schema` 必须用 `|safe` 输出（内容是完整 HTML/JSON-LD 片段）。`post.html`、`list.html` 等子模板**不要**重复输出这两个插槽——它们只在 `base.html` 出现一次。

### 404.html 错误页契约（404 与 500 共用）

核心异常处理器（`dawn_main.py` 的 `app.exception_handlers[404]/[500]`）会优先用当前主题渲染 `templates/404.html`，渲染失败或主题缺失时逐级回退：默认主题（shimo）的 404.html → 内置 FastHTML 错误页。错误页自动带 `noindex, nofollow`。

除 `_dawn_ctx()` 站点变量外，额外注入：

| 变量 | 内容 |
|---|---|
| `error_code` | 404 或 500（int） |
| `error_title` | 中文标题（如「页面不存在」） |
| `error_message` | 中文描述 |
| `request_path` | 触发错误的 URL 路径（如 `/no-such-page`） |

推荐写法（多语言 + 404/500 共用一个模板）：

```html
{% extends "base.html" %}
{% block content %}
<h1>{{ error_code }}</h1>
<p>{% if error_code == 404 %}{{ t('err404_title', error_title) }}{% else %}{{ t('err500_title', error_title) }}{% endif %}</p>
<a href="/">{{ t('back_home', '返回首页') }}</a>
{% endblock %}
```

配套 locale 键（6 个内置主题均已内置 zh/en/ja/zh-TW）：`err_eyebrow`、`err404_title`、`err404_desc`、`err404_poem`（主题个性化一句）、`err500_title`、`err500_desc`、`err_docs`；`back_home` 复用已有键。第三方主题可只写中文默认值，其余语言走 `t(key, default)` 兜底。

## 主题设置（theme.json settings）

主题可声明自定义设置项，后台「外观主题」页自动渲染表单，值按主题隔离存储（切换主题不丢），模板内通过 `theme_settings.名称` 读取：

```json
"settings": {
  "accent_color": { "type": "color", "label": "强调色", "default": "#10b315", "description": "..." },
  "default_color_scheme": { "type": "select", "label": "默认配色", "options": ["Light", "Dark", "System"], "default": "Light" },
  "tagline_text": { "type": "text", "label": "标语", "default": "", "placeholder": "..." },
  "dark_theme_logo": { "type": "image", "label": "暗色 Logo", "default": "", "description": "填 /static/... 或完整 URL" }
}
```

- 四种类型：`select`（校验选项）、`color`（校验 hex）、`text`（≤500 字符）、`image`（须 / 或 http 开头）
- `accent_color` / `dark_theme_accent_color` / `body_font` / `headings_font` 是**平台级生效**的：`dawn_theme_root_css()` 会派生 :root / html.dark 变量覆盖（accent-deep/accent-soft 由 color-mix 自动派生），非系统字体自动注入 Google Fonts @import
- 其余设置项由模板自行消费（`theme_settings.xxx`）
- 存储键：`site_settings` 表 `theme_{主题key}_set_{名称}`

参考实现：`themes/owenboker/`（12 项设置全示例）。

## 三步上线

1. 后台 → 外观 → 「上传主题包 zip」→ 选择文件
2. 校验通过后主题出现在卡片列表
3. 点击卡片即切换，前台立即生效，无需重启

## 上传限制

- zip ≤ 4MB，解压后 ≤ 120 个文件
- 文件后缀白名单：json / html / css / js / md / txt / svg / png / jpg / jpeg / webp / gif / ico / woff / woff2 / ttf / otf
- 自动剥离单层包裹目录（`sakura/theme.json` 和 `theme.json` 两种打包方式都认）
- 路径穿越（`../`）直接拒绝
- 模板加载失败自动回滚删除，不会留下坏主题
- 上传成功后自动调用 `dawn_reload_themes()` 清缓存，无需重启

## 作用范围

主题只影响前台：首页、分类页、标签页、文章页、关于页、搜索页、登录注册页。后台管理界面固定暗色，不受主题影响。

---

下一篇：[变量参考：全部 28 个 token](/docs/tokens)
