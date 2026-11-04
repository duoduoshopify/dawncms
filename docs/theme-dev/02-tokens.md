# 变量参考：全部 28 个 token

`vars.json` 里可以写以下 28 个变量。未填写的自动继承默认值（宣纸风）；有 `extends` 时先继承父主题的 vars。

> 注意：token 名在 vars.json 里用下划线（`ink_soft`），注入到 CSS 时自动转连字符（`--ink-soft`）。

## 背景与卡片

| 变量 | 默认值 | 用途 |
|---|---|---|
| `paper` | `#f8f6f1` | 页面大背景，同时用作深色按钮上的文字色 |
| `card` | `#fffdf9` | 卡片、面板背景 |
| `wash` | `#f0ede5` | 引用块等衬底区域、搜索框底 |

## 文字（从深到浅六级）

| 变量 | 默认值 | 用途 |
|---|---|---|
| `ink` | `#23211d` | 主墨色：标题、按钮底色 |
| `ink_soft` | `#3a372f` | 正文文字 |
| `ink_2` | `#5a554a` | 次要文字：导航链接、摘要 |
| `muted` | `#8a857a` | 弱化文字：副标题 |
| `faint` | `#a8a398` | 更弱：日期、阅读数 |
| `ghost` | `#c6c1b5` | 最弱：禁用态、占位 |

## 强调色

| 变量 | 默认值 | 用途 |
|---|---|---|
| `accent` | `#b4362e` | 朱砂：链接、标签、激活态、阅读进度条 |
| `accent_deep` | `#93291f` | accent 的 hover 深色 |
| `accent_soft` | `#f7ebe9` | accent 的浅衬底（TOC 高亮、引用块） |
| `accent_rgb` | `180,54,46` | accent 的 RGB 三元组，用于 rgba 透明叠加 |

## 边框（发丝三级）

| 变量 | 默认值 | 用途 |
|---|---|---|
| `hairline` | `#e5e1d6` | 主发丝边框：卡片、分隔线 |
| `hairline_soft` | `#efece3` | 更浅：图片分隔线 |
| `hairline_strong` | `#cfc9ba` | 卡片 hover 时的边框 |

## 代码与高亮

| 变量 | 默认值 | 用途 |
|---|---|---|
| `code_bg` | `#efece3` | 行内代码背景 |
| `code_text` | `#8a2f28` | 行内代码文字 |
| `hl_yellow` | `#efe7c8` | 高亮标记·黄 |
| `hl_green` | `#dfe8d8` | 高亮标记·绿 |
| `hl_red` | `#f0dcd8` | 高亮标记·红 |
| `hl_purple` | `#e6def0` | 高亮标记·紫 |

## RGB 三元组

格式必须是 `R,G,B` 纯数字，用于 `rgba(var(--accent-rgb), .18)` 这类透明叠加：

| 变量 | 默认值 | 用途 |
|---|---|---|
| `accent_rgb` | `180,54,46` | 选中区底色、强调色透明叠加 |
| `ink_rgb` | `35,33,29` | 卡片阴影色 |
| `muted_rgb` | `138,133,122` | 滚动条色 |

## 字体栈

| 变量 | 默认值 | 用途 |
|---|---|---|
| `serif` | 宋体系衬线栈 | 标题字体（`.ff-serif`） |
| `doc_font` | 宋体系衬线栈 | 文章正文字体 |

参考字体栈：

```
衬线：'Noto Serif SC','Songti SC','SimSun',Georgia,serif
无衬线：-apple-system,BlinkMacSystemFont,'PingFang SC','Microsoft YaHei',sans-serif
```

## 标签

| 变量 | 默认值 | 用途 |
|---|---|---|
| `tag_bg` | `#f0ede5` | 标签 chip 背景 |
| `tag_text` | `#6b675e` | 标签 chip 文字 |

## 联动关系

- `paper`：除了页面背景，还是深色按钮上的文字色
- `ink`：除了标题色，还是主按钮底色
- 三个 `_rgb` 变量必须和对应 hex 值保持一致，否则透明叠加处会偏色

---

上一篇：[快速上手](/docs/quick-start) ｜ 下一篇：[设计指南](/docs/design-guide)
