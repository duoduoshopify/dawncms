# 上传、调试与 FAQ

## 上传流程

**主题包 zip**（推荐，功能最全）：

1. 本地建好主题目录（见[快速上手](/docs/quick-start)），打成 zip
2. 后台 → 外观 → 「上传主题包 zip」→ 选择文件（≤4MB、≤120 个文件）
3. 校验通过后解压到 `themes/custom/{key}/`，卡片列表出现
4. 点击卡片即切换，前台立即生效（上传/切换都会自动清主题缓存，无需重启）


迭代方式：同名 key 重新上传即覆盖。删除在主题卡片下方；删的是当前使用中的主题会自动回退默认主题。

## zip 打包注意

两种结构都支持：

```
方式一（裸文件）        方式二（单层包裹目录）
theme.json             my-theme/theme.json
vars.json              my-theme/vars.json
templates/...          my-theme/templates/...
```

`macOS` 打包请排除 `__MACOSX` 和 `.DS_Store`：`zip -r theme.zip my-theme -x "*.DS_Store"`

## 用 DevTools 实时调色

最快的设计迭代方式不是改文件再上传，而是先在浏览器里调：

1. 打开前台任意页面 → F12 → Elements
2. 选中 `<html>` 元素，右侧 Styles 面板找到 `:root`
3. 直接改 `--ink`、`--accent` 等变量值，页面实时变化
4. 调满意后把最终值抄回 `vars.json` 再上传

## 模板调试

- 模板语法错误会在**上传时**被拦截（加载失败自动回滚），不会带病上线
- 渲染用的是 Jinja2 沙盒环境：`{{ }}` 变量、 `{% if/for %}` 都可用，但不能访问 Python 对象属性（如 `a.__class__`）
- 模板可用上下文见 `routes/dawn_frontend.py` 的 `_dawn_ctx()` / `_dawn_list_response()` / 文章路由，或者直接读 `themes/shimo/templates/` 里现有模板的用法
- 改了 `themes/` 目录里内置主题的文件后，调用 `dawn_themes.dawn_reload_themes()` 或重启服务生效
- 主题文件的版权头/标识遵循 DawnCMS 命名约定：文件 `dawn_xxx.py`、模块级函数 `dawn_xxx`、私有 `_dawn_xxx`、类 `DawnXxx`、常量 `DAWN_XXX`（主题模板内的 Jinja 变量不受影响）

## 常见问题

**上传报「theme.json 缺失/不合法」？**
检查 json 语法、`key` 是否匹配 `^[a-z0-9][a-z0-9-]{1,31}$`、`name` 是否存在。

**报「必须包含 templates/base.html」？**
没写 `extends` 的主题必须自带完整模板。只想改配色就加 `"extends": "shimo"`。

**RGB 三元组怎么填？**
`accent_rgb`、`ink_rgb`、`muted_rgb` 必须是 `R,G,B` 纯数字（如 `180,54,46`），不要写成 hex 或 `rgb(...)`。

**为什么我的变量没生效？**
- token 名拼写：必须是 28 个 token 之一（下划线命名）
- 浏览器缓存：`Ctrl+Shift+R` 强制刷新
- 继承顺序：子主题 vars > 父主题 vars > 默认值

**主题会影响后台吗？**
不会。后台管理界面固定暗色。主题只作用于前台公开页面。

**SEO 插件装了但没输出 hreflang / schema？**
检查主题 `base.html` 是否包含 head 插槽契约（`extra_head`、`site_schema`、`robots_meta` 等，见[快速上手](/docs/quick-start)的插槽契约一节）。缺失不会报错，只是静默跳过。另外 `extra_head`/`site_schema` 必须加 `|safe`，且不要在子模板里重复输出。

**页脚 "Powered by DawnCMS" 可以去掉吗？**
可以，自己主题的 `partials/footer.html` 自由发挥；内置 6 个主题默认带 DawnCMS 页脚署名。

**封面图会跟着主题变吗？**
内置演示封面会：`/uploads/blog/covers/series-XX.svg` 形式的演示封面在渲染时自动解析到 `covers/{当前主题}/` 下的同名主题版（存在才替换）。你自己上传的封面是静态文件（`static/uploads/blog/`），保持不变。

**主题自带的字体/图片怎么引用？**
放在 `assets/` 下，经 `/theme-assets/{key}/{path}` 访问（如 `/theme-assets/sakura/fonts/xxx.woff2`）；模板里推荐用 `logo_url` 变量引用 logo（自动沿继承链查找并回退）。MIME 有白名单，缓存 1 天。

**主题的 UI 文案怎么做多语言？**
在 `locales/` 放 `{lang}.json`（如 `en.json`、`zh-TW.json`），模板用 `{{ t("nav.home", "首页") }}` 输出。中文默认表命名为 `zh-CN.default.json`。不写 locales 也能跑——i18n 插件提供兜底表。

## 数据存储位置

| 数据 | 位置 |
|---|---|
| 内置主题 | `themes/{key}/` 目录（theme.json + vars.json + assets/ + locales/ + templates/） |
| 上传的主题包 | `themes/custom/{key}/` 目录 |
| 主题静态资产服务 | 路由 `/theme-assets/{key}/{path}`（沿继承链查找，缓存 1 天） |
| 当前主题 | `site_settings` 表，key = `theme` |
| 版式（宽/窄） | `site_settings` 表，key = `layout_mode`（书函 1200px / 铺陈宽幕 1560px） |

---

上一篇：[设计指南](/docs/design-guide) ｜ 返回：[文档中心](/docs)
