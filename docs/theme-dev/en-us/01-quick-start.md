# Quick Start: Build a Theme Package in 10 Minutes

DawnCMS themes are **Ghost-style theme packages**: a folder (or zip) containing metadata, color variables, static assets, locale strings, and Jinja2 templates. To restyle colors you only need two or three files; to change structure, bring your own templates.

## Theme Package Structure (same as built-in themes)

Using the built-in theme shimo as reference, the full structure looks like this (everything except `theme.json` is optional):

```
my-theme/
├── theme.json          # Required: metadata
├── vars.json           # Optional: CSS variable overrides (28 tokens)
├── style.css           # Optional: extra CSS at root (backward compatible with old packages)
├── assets/
│   ├── core/           # Optional: platform baseline (base.css / doc.css / doc.js / list.css)
│   │                   #       a same-named file overrides the baseline
│   ├── css/            # Optional: theme stylesheets; multiple .css files concatenated by filename (e.g. main.css)
│   ├── js/             # Optional: theme scripts; multiple .js files concatenated by filename (e.g. theme.js)
│   ├── fonts/          # Optional: font files (woff2 etc.)
│   └── img/            # Optional: images (logo.svg etc.)
├── locales/            # Optional: frontend UI translations ({lang}.json, see "i18n" below)
└── templates/          # Optional: Jinja2 templates (base.html required when no extends)
    ├── base.html
    ├── list.html       # Shared by home / category / tag / search
    ├── post.html       # Article page
    ├── gate.html       # Member gate page
    ├── page.html       # Generic page (About etc.)
    ├── 404.html        # Error page (shared by 404 and 500, optional; falls back to the default theme's template)
    └── partials/       # nav.html / footer.html / post_card.html
```

## Loading & Merging Rules

The inheritance chain is "child theme → parent theme (extends) → defaults", and different assets merge differently:

| Asset | Merge strategy |
|---|---|
| `vars.json` | Defaults → parent → child, token by token (hyphens in keys auto-convert to underscores) |
| `style.css` + `assets/css/*.css` | **Concatenated along the chain**: parent first, child last (child overrides parent); files within css/ sorted by filename |
| `assets/js/*.js` | Same as CSS: concatenated along the chain, sorted by filename, injected as `theme_js` |
| `templates/` | Looked up along the chain, **child first** (Jinja2 FileSystemLoader hits directories in order) |
| `assets/core/*` | Platform baseline files (doc styles/scripts etc.), same-name lookup along the chain, child first |
| `assets/` static files | Served via `/theme-assets/{key}/{path}` (chain lookup, MIME whitelist, 1-day cache) |
| `locales/*.json` | Merged along the chain (parent first, child overrides same keys) |

## i18n (locales/)

Frontend UI strings (navigation, buttons, etc.) are rendered via `t("key", "default")` in templates, with translation tables from the theme's `locales/` directory:

- Filenames follow BCP 47: `en.json`, `zh-TW.json`, `ja.json`…
- **The Chinese default table has the special name `zh-CN.default.json`** (it's the fallback table, not a "translation")
- Fallback chain: `en-us` → `[en-us, en-US, en]`, level by level
- Third-party themes without `locales/` still work — the i18n plugin registers a fallback table via `dawn_register_locale_provider`

## The Three Sources of Themes

| Source | Location | Notes |
|---|---|---|
| Built-in themes | `themes/{key}/` | Shipped with the code: shimo / baiye / noir / mori / classic / sudo / owenboker |
| Uploaded packages | Admin → Appearance, upload zip | Extracted to `themes/custom/{key}/` |
| Active theme | `site_settings` table | Click a card in admin to switch, no restart needed |

## Minimal Theme: Colors Only

Use `extends` to inherit another theme's templates/assets/locales, and override only variables:

**theme.json**

```json
{
  "key": "sakura",
  "name": "Sakura",
  "description": "Cherry-pink base with crimson accents",
  "author": "you",
  "version": "1.0",
  "extends": "shimo",
  "preview": ["#fdf2f4", "#3d2c31", "#d16b86"]
}
```

**vars.json** (only the tokens you override; the rest inherit defaults)

```json
{
  "paper": "#fdf2f4",
  "accent": "#d16b86",
  "accent_rgb": "209,107,134"
}
```

Zip it and upload. Full example: `examples/theme-sakura.zip`.

- `key`: unique identifier, 2–32 lowercase letters/digits/hyphens (regex `^[a-z0-9][a-z0-9-]{1,31}$`)
- `extends`: parent theme key. Templates/vars/CSS/JS/locales/assets all fall back along the chain (child → parent → defaults)
- Without `extends`, **you must ship your own `templates/base.html`**, or validation fails

## Full Theme: Bring Your Own Templates

Copy the whole `themes/shimo/templates/` set and modify. Templates use Jinja2 and render in a **sandboxed environment** (dangerous operations like attribute traversal are blocked). Available variables are documented in the comments at the top of each template.

`dawn_render()` automatically injects the following context into every template (no explicit passing needed in routes):

| Variable | Content |
|---|---|
| `theme_key` | Current theme key |
| `t` | Translation function `t("key", "default")`, reading `locales/` and the plugin fallback table |
| `theme_js` | Concatenated `assets/js/*.js` along the inheritance chain |
| `logo_url` | `/theme-assets/` URL of `assets/img/logo.svg` (falls back to `/static/logo.svg`) |

In addition, `_dawn_ctx()` in `routes/dawn_frontend.py` injects site-level variables (`site_name` / `page_title` / `canonical` / `site_schema` / `og_image` / `og_locale`, etc.).

### base.html head slot contract (required by SEO/GEO plugins)

A third-party theme's `base.html` must keep the following slots, or SEO/GEO plugins and i18n features will silently stop working (no errors, just no output):

```html
{% if canonical %}<link rel="canonical" href="{{ canonical }}">{% endif %}
<meta property="og:locale" content="{{ og_locale or 'zh_CN' }}">
{% for ol in og_locale_alternates or [] %}<meta property="og:locale:alternate" content="{{ ol }}">{% endfor %}
<meta property="og:image" content="{{ og_image or (site_base_url + '/static/logo.svg') }}">
{% if robots_meta %}<meta name="robots" content="{{ robots_meta }}">{% endif %}
{% if extra_head %}{{ extra_head|safe }}{% endif %}
{% if site_schema %}{{ site_schema|safe }}{% endif %}
```

| Slot | Source | Purpose |
|---|---|---|
| `canonical` | Core page routes | Self-referencing canonical; i18n translated pages point to the translated URL |
| `og_locale` / `og_locale_alternates` | Core `_dawn_ctx` / i18n plugin | OG locale tags (`zh_CN` ↔ `en_US`) |
| `og_image` | Core default logo; seogeo plugin can override | Social share image |
| `robots_meta` | Core (noindex on search/auth pages) + article routes | robots directives |
| `extra_head` | Core (article JSON-LD) + `head_extra` hook | seogeo/i18n plugins inject hreflang, verification meta, etc. |
| `site_schema` | Core `_dawn_ctx`; seogeo plugin can rebuild | Site-level Organization/WebSite JSON-LD |

Note: `extra_head` and `site_schema` must be output with `|safe` (they contain complete HTML/JSON-LD fragments). Child templates like `post.html` and `list.html` must **not** output these slots again — they appear only once in `base.html`.

### 404.html error page contract (shared by 404 and 500)

The core exception handlers (`app.exception_handlers[404]/[500]` in `dawn_main.py`) prefer rendering the active theme's `templates/404.html`, falling back step by step on failure: default theme (shimo) 404.html → built-in FastHTML error page. Error pages automatically carry `noindex, nofollow`.

Besides the `_dawn_ctx()` site variables, these are injected:

| Variable | Content |
|---|---|
| `error_code` | 404 or 500 (int) |
| `error_title` | Title (e.g. "Page not found") |
| `error_message` | Description |
| `request_path` | The URL path that triggered the error (e.g. `/no-such-page`) |

Recommended pattern (i18n + one template for both 404/500):

```html
{% extends "base.html" %}
{% block content %}
<h1>{{ error_code }}</h1>
<p>{% if error_code == 404 %}{{ t('err404_title', error_title) }}{% else %}{{ t('err500_title', error_title) }}{% endif %}</p>
<a href="/">{{ t('back_home', 'Back to home') }}</a>
{% endblock %}
```

Locale keys (all built-in themes ship zh/en/ja/zh-TW): `err_eyebrow`, `err404_title`, `err404_desc`, `err404_poem` (one theme-flavored line), `err500_title`, `err500_desc`, `err_docs`; `back_home` reuses the existing key. Third-party themes may provide only the Chinese defaults — other languages fall back via `t(key, default)`.

## Theme Settings (theme.json settings)

A theme can declare custom settings. The admin Appearance page renders the form automatically; values are stored per theme (switching themes doesn't lose them), and templates read them via `theme_settings.name`:

```json
"settings": {
  "accent_color": { "type": "color", "label": "Accent color", "default": "#10b315", "description": "..." },
  "default_color_scheme": { "type": "select", "label": "Default scheme", "options": ["Light", "Dark", "System"], "default": "Light" },
  "tagline_text": { "type": "text", "label": "Tagline", "default": "", "placeholder": "..." },
  "dark_theme_logo": { "type": "image", "label": "Dark logo", "default": "", "description": "Use /static/... or a full URL" }
}
```

- Four types: `select` (validates options), `color` (validates hex), `text` (≤500 chars), `image` (must start with / or http)
- `accent_color` / `dark_theme_accent_color` / `body_font` / `headings_font` take effect **at the platform level**: `dawn_theme_root_css()` derives :root / html.dark variable overrides (accent-deep/accent-soft are auto-derived via color-mix), and non-system fonts get a Google Fonts @import injected
- All other settings are consumed by templates themselves (`theme_settings.xxx`)
- Storage key: `site_settings` table, `theme_{themekey}_set_{name}`

Reference implementation: `themes/owenboker/` (a full 12-setting example).

## Launch in Three Steps

1. Admin → Appearance → "Upload theme zip" → choose file
2. After validation passes, the theme appears in the card list
3. Click the card to switch — the frontend updates immediately, no restart

## Upload Limits

- zip ≤ 4MB, ≤ 120 files after extraction
- Extension whitelist: json / html / css / js / md / txt / svg / png / jpg / jpeg / webp / gif / ico / woff / woff2 / ttf / otf
- Single wrapping directory is auto-stripped (both `sakura/theme.json` and bare `theme.json` are accepted)
- Path traversal (`../`) is rejected outright
- If template loading fails, the upload rolls back automatically — no broken theme left behind
- After a successful upload, `dawn_reload_themes()` clears caches automatically — no restart needed

## Scope

Themes only affect the frontend: home, category, tag, article, about, search, login/register pages. The admin interface has a fixed dark style and is not affected by themes.

---

Next: [Token Reference: all 28 tokens](/en-us/docs/tokens)
