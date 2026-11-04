# Design Guide: Making a Theme That Ages Well

A good theme isn't "swap a few colors" — it's a set of decisions that cooperate. This chapter covers the trade-offs.

## Choose Your Route First: Reskin or Rebuild

| Need | Approach |
|---|---|
| Change colors / fonts only | `vars.json` + `extends` — two files and done |
| Tweak styles (radius, shadows, hover) | Add `assets/css/main.css` (or root `style.css`), override by class name |
| Change layout structure (sidebar, grid, nav) | Bring your own `templates/`; reference shimo or baiye |
| Override the platform baseline (body typography / doc styles) | Drop a same-named file in `assets/core/` (e.g. `doc.css`) |

The built-in "shimo" and "baiye" themes are complete examples of the two routes: same data context — shimo goes centered-magazine, baiye goes left-catalog + right-grid.

## Contrast Is the Bottom Line

- `ink` vs `paper` contrast **≥ 7:1** — body text stays comfortable over long reads
- `accent` vs `paper` contrast **≥ 4.5:1** — links and small labels stay legible
- Recommended tool: WebAIM Contrast Checker

The six text levels (ink → ghost) keep their hierarchy through a grayscale ladder; aim for roughly 15% lightness difference between adjacent levels.

## Light Theme Techniques

- `hairline` should be close to `paper` but just barely visible — the point of a hairline border is "structure you almost can't see"
- `wash` sits between `paper` and `hairline`, used as the quote-block substrate
- The accent can run slightly darker — saturated colors already pop on a white base

## Dark Theme Techniques

- Don't use pure black for `paper`: a blue-tinted black ages better
- Inline code `code_bg` should be slightly brighter than `paper` so it lifts off the background
- Raise `accent` brightness a bit (colors read darker on dark backgrounds)
- Pure white text is harsh; use an off-white like `#e8e4da` for `ink`

See the built-in `noir` theme — it's the canonical dark treatment.

## Font Decisions

| Style | serif | doc_font |
|---|---|---|
| Chinese-literati / magazine | Serif stack | Serif stack |
| Tech / minimal / tool | Sans stack | Sans stack |
| Compromise | Serif stack | Sans stack |

A Chinese serif body has a lovely bookish feel, but below 15px it gets muddy — the article body default of ~17px is deliberate.

## Writing style.css / assets/css

- Change `vars.json` for variables; reserve CSS files for layout and behavior (hover, shadows, transform)
- Templates use Tailwind arbitrary values like `bg-[var(--paper)]` extensively, so changing a token applies globally
- Common hook classes: `.paper-card` (cards), `.cat-tab` (category pills), `.doc-content` (body container), `.toc-link` (TOC items), `.doc-progress` (reading progress bar), `.eyebrow` (eyebrow label)
- CSS/JS concatenate along the inheritance chain (parent first, child last), so at equal specificity your rules naturally beat the parent theme — no `!important` needed; prefix with `body` when you need extra weight

## Checklist

- [ ] Home: heading, excerpt, date, and category entries have clear hierarchy
- [ ] Article page: H2 side bars, quote blocks, inline code, and code blocks are all distinguishable
- [ ] Buttons: text on dark buttons is readable (`paper` as text color)
- [ ] Text selection (::selection) color is harmonious
- [ ] Member badges and tag chips don't look out of place on cards
- [ ] TOC highlight and reading progress bar match accent

---

Previous: [Token Reference](/en-us/docs/tokens) ｜ Next: [Upload, Debugging & FAQ](/en-us/docs/upload-debug)
