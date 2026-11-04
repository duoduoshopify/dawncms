# Upload, Debugging & FAQ

## Upload Flow

**Theme package zip** (recommended, full-featured):

1. Build the theme directory locally (see [Quick Start](/en-us/docs/quick-start)), zip it
2. Admin → Appearance → "Upload theme zip" → choose file (≤4MB, ≤120 files)
3. After validation it extracts to `themes/custom/{key}/` and appears in the card list
4. Click the card to switch — the frontend updates immediately (upload and switching both clear the theme cache automatically, no restart)


Iteration: re-uploading the same key overwrites. Deletion is below the theme card; deleting the currently active theme auto-falls-back to the default theme.

## Zip Packaging Notes

Both structures are supported:

```
Option 1 (bare files)      Option 2 (single wrapping dir)
theme.json                 my-theme/theme.json
vars.json                  my-theme/vars.json
templates/...              my-theme/templates/...
```

On macOS, exclude `__MACOSX` and `.DS_Store`: `zip -r theme.zip my-theme -x "*.DS_Store"`

## Live Color Tuning with DevTools

The fastest design iteration isn't edit-file-then-upload — it's tuning in the browser first:

1. Open any frontend page → F12 → Elements
2. Select the `<html>` element, find `:root` in the Styles panel on the right
3. Edit `--ink`, `--accent`, etc. directly — the page updates live
4. When happy, copy the final values back into `vars.json` and upload

## Template Debugging

- Template syntax errors are intercepted **at upload time** (failed loads roll back automatically) — broken themes never go live
- Rendering uses a Jinja2 sandbox: `{{ }}` variables and `{% if/for %}` work, but Python attribute access is blocked (e.g. `a.__class__`)
- For available template context, see `_dawn_ctx()` / `_dawn_list_response()` / the article route in `routes/dawn_frontend.py`, or read the existing templates in `themes/shimo/templates/`
- After editing files of built-in themes under `themes/`, call `dawn_themes.dawn_reload_themes()` or restart the service
- Copyright headers / identifiers in theme files follow the DawnCMS naming convention: files `dawn_xxx.py`, module-level functions `dawn_xxx`, private `_dawn_xxx`, classes `DawnXxx`, constants `DAWN_XXX` (Jinja variables inside theme templates are not affected)

## FAQ

**Upload fails with "theme.json missing/invalid"?**
Check JSON syntax, that `key` matches `^[a-z0-9][a-z0-9-]{1,31}$`, and that `name` exists.

**Fails with "must contain templates/base.html"?**
Themes without `extends` must ship complete templates. If you only want to change colors, add `"extends": "shimo"`.

**How do I fill RGB triplets?**
`accent_rgb`, `ink_rgb`, `muted_rgb` must be pure `R,G,B` digits (e.g. `180,54,46`) — not hex, not `rgb(...)`.

**Why aren't my variables taking effect?**
- Token spelling: must be one of the 28 tokens (underscore naming)
- Browser cache: hard-refresh with `Ctrl+Shift+R`
- Inheritance order: child theme vars > parent theme vars > defaults

**Do themes affect the admin panel?**
No. The admin interface has a fixed dark style. Themes only apply to public frontend pages.

**SEO plugin installed but no hreflang / schema output?**
Check whether your theme's `base.html` includes the head slot contract (`extra_head`, `site_schema`, `robots_meta`, etc. — see the slot contract section in [Quick Start](/en-us/docs/quick-start)). Missing slots fail silently. Also `extra_head`/`site_schema` must use `|safe`, and must not be output again in child templates.

**Can I remove the "Powered by DawnCMS" footer?**
Yes — your own theme's `partials/footer.html` is entirely yours. The built-in themes ship with a DawnCMS footer credit by default.

**Do cover images follow the theme?**
The built-in demo covers do: demo cover paths like `/uploads/blog/covers/series-XX.svg` resolve at render time to `covers/{active-theme}/` when a themed variant exists. Covers you upload yourself are static files under `static/uploads/blog/` and stay as-is.

**How do I reference a theme's own fonts/images?**
Put them under `assets/` and access them via `/theme-assets/{key}/{path}` (e.g. `/theme-assets/sakura/fonts/xxx.woff2`); in templates, prefer the `logo_url` variable for the logo (it looks up the inheritance chain with fallback). MIME types are whitelisted; cache is 1 day.

**How do I translate a theme's UI strings?**
Put `{lang}.json` files (e.g. `en.json`, `zh-TW.json`) in `locales/`, and output strings with `{{ t("nav.home", "Home") }}` in templates. The Chinese default table is named `zh-CN.default.json`. Themes without locales still work — the i18n plugin provides a fallback table.

## Where Data Lives

| Data | Location |
|---|---|
| Built-in themes | `themes/{key}/` (theme.json + vars.json + assets/ + locales/ + templates/) |
| Uploaded theme packages | `themes/custom/{key}/` |
| Theme static asset serving | Route `/theme-assets/{key}/{path}` (chain lookup, 1-day cache) |
| Active theme | `site_settings` table, key = `theme` |
| Layout (narrow/wide) | `site_settings` table, key = `layout_mode` (1200px / 1560px) |

---

Previous: [Design Guide](/en-us/docs/design-guide) ｜ Back to: [Docs Center](/en-us/docs)
