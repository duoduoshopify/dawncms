# Token Reference: All 28 Tokens

You can write the following 28 variables in `vars.json`. Anything you leave out inherits the default (rice-paper style); with `extends`, the parent theme's vars are inherited first.

> Note: token names use underscores in vars.json (`ink_soft`) and are auto-converted to hyphens when injected into CSS (`--ink-soft`).

## Backgrounds & Cards

| Variable | Default | Purpose |
|---|---|---|
| `paper` | `#f8f6f1` | Page background; also the text color on dark buttons |
| `card` | `#fffdf9` | Card and panel backgrounds |
| `wash` | `#f0ede5` | Substrate areas like quote blocks; search box background |

## Text (six levels, dark to light)

| Variable | Default | Purpose |
|---|---|---|
| `ink` | `#23211d` | Primary ink: headings, button background |
| `ink_soft` | `#3a372f` | Body text |
| `ink_2` | `#5a554a` | Secondary text: nav links, excerpts |
| `muted` | `#8a857a` | De-emphasized text: subtitles |
| `faint` | `#a8a398` | Even weaker: dates, view counts |
| `ghost` | `#c6c1b5` | Weakest: disabled states, placeholders |

## Accent

| Variable | Default | Purpose |
|---|---|---|
| `accent` | `#b4362e` | Vermilion: links, tags, active states, reading progress bar |
| `accent_deep` | `#93291f` | Darker hover shade of accent |
| `accent_soft` | `#f7ebe9` | Light accent substrate (TOC highlight, quote blocks) |
| `accent_rgb` | `180,54,46` | RGB triplet of accent, for rgba overlays |

## Borders (three hairline levels)

| Variable | Default | Purpose |
|---|---|---|
| `hairline` | `#e5e1d6` | Primary hairline border: cards, dividers |
| `hairline_soft` | `#efece3` | Lighter: image separators |
| `hairline_strong` | `#cfc9ba` | Card border on hover |

## Code & Highlight

| Variable | Default | Purpose |
|---|---|---|
| `code_bg` | `#efece3` | Inline code background |
| `code_text` | `#8a2f28` | Inline code text |
| `hl_yellow` | `#efe7c8` | Highlight marker · yellow |
| `hl_green` | `#dfe8d8` | Highlight marker · green |
| `hl_red` | `#f0dcd8` | Highlight marker · red |
| `hl_purple` | `#e6def0` | Highlight marker · purple |

## RGB Triplets

Format must be pure `R,G,B` digits, used for transparent overlays like `rgba(var(--accent-rgb), .18)`:

| Variable | Default | Purpose |
|---|---|---|
| `accent_rgb` | `180,54,46` | Selection background, accent transparent overlays |
| `ink_rgb` | `35,33,29` | Card shadow color |
| `muted_rgb` | `138,133,122` | Scrollbar color |

## Font Stacks

| Variable | Default | Purpose |
|---|---|---|
| `serif` | Songti-style serif stack | Heading font (`.ff-serif`) |
| `doc_font` | Songti-style serif stack | Article body font |

Reference font stacks:

```
Serif: 'Noto Serif SC','Songti SC','SimSun',Georgia,serif
Sans:  -apple-system,BlinkMacSystemFont,'PingFang SC','Microsoft YaHei',sans-serif
```

## Tags

| Variable | Default | Purpose |
|---|---|---|
| `tag_bg` | `#f0ede5` | Tag chip background |
| `tag_text` | `#6b675e` | Tag chip text |

## Interplay

- `paper`: besides the page background, it's also the text color on dark buttons
- `ink`: besides heading color, it's the primary button background
- The three `_rgb` variables must stay consistent with their hex counterparts, or transparent overlays will shift color

---

Previous: [Quick Start](/en-us/docs/quick-start) ｜ Next: [Design Guide](/en-us/docs/design-guide)
