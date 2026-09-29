---
version: alpha
name: IT-Movies-design-analysis
description: "A curated catalog of films, series and documentaries about computers, technology and AI. The system reads as a clean, content-first editorial surface — light paper-white canvas with a subtle dot-grid texture, deep ink text, and a single green accent reserved for brand marks and primary actions. Dark mode mirrors the same structure with lifted charcoal surfaces. Typography is set in Ubuntu (400/500/700) with Cyrillic and Latin subsets. Cards use a 96px poster column with hairline borders and a quiet hover lift."

colors:
  accent: "#147a3d"
  accent-hover: "#1a8f47"
  accent-ink: "#ffffff"
  bg: "#f0f2f5"
  paper: "#fbfaf7"
  paper-strong: "#ffffff"
  ink: "#171923"
  muted: "#5c6370"
  line: "#e2e5ea"
  line-strong: "#c8cdd5"
  kp: "#a54b12"
  imdb: "#856414"
  signal: "#c0392b"
  icon: "#2563eb"
  focus: "#147a3d"
  glass: "rgba(251, 250, 247, 0.85)"
  glass-card: "rgba(251, 250, 247, 0.95)"
  shadow: "rgba(23, 25, 35, 0.08)"
  dot: "rgba(23, 25, 35, 0.06)"
  dark-bg: "#0f1115"
  dark-paper: "#16181d"
  dark-paper-strong: "#1c1f26"
  dark-ink: "#e8eaf0"
  dark-muted: "#9aa0ab"
  dark-line: "#2a2d35"
  dark-line-strong: "#3a3d47"
  dark-accent: "#35b96a"
  dark-kp: "#d4762c"
  dark-imdb: "#c9a227"
  dark-glass: "rgba(22, 24, 29, 0.85)"
  dark-glass-card: "rgba(22, 24, 29, 0.95)"
  dark-shadow: "rgba(0, 0, 0, 0.3)"
  dark-dot: "rgba(232, 234, 240, 0.04)"

typography:
  display:
    fontFamily: Ubuntu
    fontSize: "1.5rem"
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "-0.02em"
  headline:
    fontFamily: Ubuntu
    fontSize: "1.25rem"
    fontWeight: 700
    lineHeight: 1.3
    letterSpacing: "-0.01em"
  card-title:
    fontFamily: Ubuntu
    fontSize: "1rem"
    fontWeight: 700
    lineHeight: 1.35
    letterSpacing: "-0.01em"
  body:
    fontFamily: Ubuntu
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: 0
  body-sm:
    fontFamily: Ubuntu
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: 1.45
    letterSpacing: 0
  caption:
    fontFamily: Ubuntu
    fontSize: "0.8125rem"
    fontWeight: 400
    lineHeight: 1.4
    letterSpacing: 0
  button:
    fontFamily: Ubuntu
    fontSize: "0.875rem"
    fontWeight: 500
    lineHeight: 1.2
    letterSpacing: 0
  badge:
    fontFamily: Ubuntu
    fontSize: "0.75rem"
    fontWeight: 500
    lineHeight: 1.2
    letterSpacing: "0.02em"

rounded:
  xs: 4px
  s: 6px
  m: 7px
  l: 8px
  xl: 12px
  circle: 50%
  pill: 999px

spacing:
  1: 4px
  2: 8px
  3: 12px
  4: 16px
  5: 20px
  6: 24px
  7: 32px
  8: 48px
  0-2: 2px
  0-35: 3.5px
  1-25: 10px
  2-25: 18px
  tap: 44px

components:
  featured-card:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.xl}"
    padding: "{spacing.6}"
    border: "1px solid {colors.line}"
    accentBorder: "2px solid {colors.accent}"
    hoverLift: "translateY(-2px)"
  rc-card:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.l}"
    padding: "{spacing.4}"
    border: "1px solid {colors.line}"
    hoverLift: "translateY(-2px)"
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.accent-ink}"
    typography: "{typography.button}"
    rounded: "{rounded.m}"
    padding: "{spacing.2} {spacing.4}"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.ink}"
    typography: "{typography.button}"
    rounded: "{rounded.m}"
    padding: "{spacing.2} {spacing.4}"
  chip:
    backgroundColor: "{colors.paper-strong}"
    textColor: "{colors.muted}"
    typography: "{typography.caption}"
    rounded: "{rounded.pill}"
    padding: "{spacing-0-35} {spacing-2}"
  input:
    backgroundColor: "{colors.paper-strong}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.m}"
    padding: "{spacing-2} {spacing-3}"
    border: "1px solid {colors.line}"
  nav-link:
    textColor: "{colors.muted}"
    typography: "{typography.button}"
    rounded: "{rounded.pill}"
    padding: "{spacing-2} {spacing-3}"
  nav-link-active:
    backgroundColor: "{colors.paper-strong}"
    textColor: "{colors.ink}"
    typography: "{typography.button}"
    rounded: "{rounded.pill}"
    padding: "{spacing-2} {spacing-3}"
  table-header:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.muted}"
    typography: "{typography.caption}"
    fontWeight: 500
  table-row:
    backgroundColor: "transparent"
    textColor: "{colors.ink}"
    typography: "{typography.body-sm}"
    borderBottom: "1px solid {colors.line}"
  badge:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.accent-ink}"
    typography: "{typography.badge}"
    rounded: "{rounded.pill}"
    padding: "{spacing-0-35} {spacing-2}"
  rating-kp:
    backgroundColor: "transparent"
    textColor: "{colors.kp}"
    typography: "{typography.caption}"
    fontWeight: 700
  rating-imdb:
    backgroundColor: "transparent"
    textColor: "{colors.imdb}"
    typography: "{typography.caption}"
    fontWeight: 700
---

## Overview

IT Movies is a curated catalog of films, series and documentaries about computers, technology and AI. The design is **content-first editorial** — a light paper-white canvas (`{colors.paper}` #fbfaf7) with a subtle dot-grid texture, deep ink text (`{colors.ink}` #171923), and a single green accent (`{colors.accent}` #147a3d) reserved for brand marks, badges, and primary actions.

The site serves two page types: a **main catalog page** with search, genre filtering, sortable tables, and a featured carousel; and **154 static film pages** each with a hero poster, metadata, ratings, description, share buttons, and related title cards.

Typography is set in **Ubuntu** (400/500/700, self-hosted woff2 with Cyrillic and Latin subsets). The type scale is compact: `--fs-xs` 0.8125rem through `--fs-xl` 1.5rem. Display and headline weights are 700; body is 400; buttons and badges are 500.

The visual rhythm is **dense but breathable** — catalog tables are the primary content, with generous section spacing and hairline dividers. Cards (featured and related) use a 96px poster column with a 1px hairline border and a quiet 2px hover lift. The accent green appears sparingly: brand mark, featured badge, fav icon, and focus rings.

**Key Characteristics:**
- **Content-first editorial** — the catalog table is the protagonist, not decorative cards.
- **Single green accent** (`{colors.accent}` #147a3d) — used only for brand, badges, and primary actions.
- **Paper-white canvas** (`{colors.paper}` #fbfaf7) with a subtle dot-grid texture.
- **Hairline borders** everywhere — 1px `{colors.line}` defines every card, table row, and input.
- **96px poster column** on every card — the image is a thumbnail, not a hero.
- **Quiet hover lift** — cards rise 2px on hover, no dramatic shadows.
- **Dark mode** mirrors the same structure with lifted charcoal surfaces.
- **No gradients, no glassmorphism, no decorative chrome** — the content is the design.

## Colors

### Brand & Accent
- **Accent Green** (`{colors.accent}`): The single chromatic accent — brand mark, featured badge, fav icon, focus rings, primary buttons.
- **Accent Hover** (`{colors.accent-hover}`): Lighter green for hover states.
- **Accent Ink** (`{colors.accent-ink}`): White text on accent surfaces.

### Surface
- **Background** (`{colors.bg}`): Page background — light gray #f0f2f5.
- **Paper** (`{colors.paper}`): Card and panel surface — warm off-white #fbfaf7.
- **Paper Strong** (`{colors.paper-strong}`): Elevated surface — pure white #ffffff.
- **Line** (`{colors.line}`): 1px borders on cards, tables, inputs.
- **Line Strong** (`{colors.line-strong}`): Stronger dividers, focus rings.
- **Dot** (`{colors.dot}`): Dot-grid texture color.

### Text
- **Ink** (`{colors.ink}`): All headlines and body text — deep near-black #171923.
- **Muted** (`{colors.muted}`): Secondary text, meta info, captions — #5c6370.

### Semantic
- **KP Orange** (`{colors.kp}`): Kinopoisk rating chips — #a54b12.
- **IMDb Gold** (`{colors.imdb}`): IMDb rating chips — #856414.
- **Signal Red** (`{colors.signal}`): Error states, destructive actions.
- **Icon Blue** (`{colors.icon}`): Informational icons, links.

### Dark Mode
- **Dark Background** (`{colors.dark-bg}`): #0f1115
- **Dark Paper** (`{colors.dark-paper}`): #16181d
- **Dark Paper Strong** (`{colors.dark-paper-strong}`): #1c1f26
- **Dark Ink** (`{colors.dark-ink}`): #e8eaf0
- **Dark Muted** (`{colors.dark-muted}`): #9aa0ab
- **Dark Line** (`{colors.dark-line}`): #2a2d35
- **Dark Accent** (`{colors.dark-accent}`): #35b96a
- **Dark KP** (`{colors.dark-kp}`): #d4762c
- **Dark IMDb** (`{colors.dark-imdb}`): #c9a227

## Typography

### Font Family
- **Ubuntu** — self-hosted woff2, weights 400/500/700, Cyrillic + Latin subsets. The only typeface.

### Hierarchy

| Token | Size | Weight | Line Height | Use |
|---|---|---|---|---|
| `{typography.display}` | 1.5rem (24px) | 700 | 1.2 | Page titles, section headings |
| `{typography.headline}` | 1.25rem (20px) | 700 | 1.3 | Card titles, table headers |
| `{typography.card-title}` | 1rem (16px) | 700 | 1.35 | Featured/related card titles |
| `{typography.body}` | 1rem (16px) | 400 | 1.5 | Default body, descriptions |
| `{typography.body-sm}` | 0.875rem (14px) | 400 | 1.45 | Table cells, meta info |
| `{typography.caption}` | 0.8125rem (13px) | 400 | 1.4 | Captions, badges, ratings |
| `{typography.button}` | 0.875rem (14px) | 500 | 1.2 | Button labels, nav links |
| `{typography.badge}` | 0.75rem (12px) | 500 | 1.2 | Type badges, count chips |

### Principles
- **Weight 700 is the display ceiling** — Ubuntu 700 for all headings, never heavier.
- **Body is always 400** — no bold body text except via `<strong>` or `<b>`.
- **Buttons and badges are 500** — the middle weight carries interactive elements.
- **Slight negative tracking on display** — -0.02em on display, -0.01em on headlines.
- **Cyrillic-first** — the site is Russian-primary; Latin is the secondary locale.

## Layout

### Spacing System
- **Base unit**: 4px. All spacing tokens are multiples of 4px.
- **Tokens**: `{spacing.1}` 4px · `{spacing.2}` 8px · `{spacing.3}` 12px · `{spacing.4}` 16px · `{spacing.5}` 20px · `{spacing.6}` 24px · `{spacing.7}` 32px · `{spacing.8}` 48px.
- **Card padding**: `{spacing.6}` 24px on featured cards; `{spacing.4}` 16px on related cards.
- **Section spacing**: `{spacing.8}` 48px between major sections.
- **Table cell padding**: `{spacing.2}` 8px vertical · `{spacing.3}` 12px horizontal.

### Grid & Container
- **Max content width**: 1080px (`--container`).
- **Featured grid**: 4 columns at desktop, 2 at tablet, 1 (carousel) at mobile.
- **Related grid**: `repeat(auto-fill, minmax(220px, 1fr))` — 4-5 columns at desktop, 2 at tablet, 1 (carousel) at mobile.
- **Film page**: CSS grid — 240px poster (mobile) / 320px poster (desktop) beside fluid info column.

### Whitespace Philosophy
- **Dense but breathable** — catalog tables are the primary content with generous row height.
- **Sections separate by spacing, not backgrounds** — no alternating section colors.
- **Cards float on paper** — 1px hairline border + 2px hover lift, no heavy shadows.

## Elevation & Depth

| Level | Treatment | Use |
|---|---|---|
| 0 (flat) | No shadow, no border | Body text, table rows |
| 1 (hairline) | 1px `{colors.line}` border | Default cards, inputs, table cells |
| 2 (lift) | 1px border + `translateY(-2px)` on hover | Featured cards, related cards |
| 3 (raised) | 1px border + subtle shadow | Modals, dialogs, popovers |

The system uses **hairline borders** as the primary depth cue, not shadows. Shadows appear only on modals and dialogs.

## Shapes

### Border Radius Scale

| Token | Value | Use |
|---|---|---|
| `{rounded.xs}` | 4px | Small chips, badges |
| `{rounded.s}` | 6px | Inline tags, rating chips |
| `{rounded.m}` | 7px | Buttons, inputs, table headers |
| `{rounded.l}` | 8px | Related cards, content panels |
| `{rounded.xl}` | 12px | Featured cards, modals |
| `{rounded.circle}` | 50% | Avatars, icon buttons |
| `{rounded.pill}` | 999px | Nav links, count badges, chips |

### Poster Geometry
- **Featured card poster**: 94×144px (2:3 aspect ratio).
- **Related card poster**: 96×144px (2:3 aspect ratio).
- **Film page hero**: 240px (mobile) / 320px (desktop) width, height auto.
- **Table poster**: 32px width, height auto.

## Components

### Featured Card (`featured-card`)
- **Layout**: `grid-template-columns: 94px 1fr` — poster left, content right.
- **Background**: `{colors.paper}` with 1px `{colors.line}` border.
- **Accent**: 2px top border in `{colors.accent}`.
- **Radius**: `{rounded.xl}` 12px.
- **Padding**: `{spacing.6}` 24px.
- **Hover**: `translateY(-2px)` lift.
- **Content**: badge (type), title (2-line clamp), meta (3-line clamp), rating chips.

### Related Card (`rc`)
- **Layout**: Row-flex — 96×144px poster left, content right.
- **Background**: `{colors.paper}` with 1px `{colors.line}` border.
- **Radius**: `{rounded.l}` 8px.
- **Padding**: `{spacing.4}` 16px.
- **Hover**: `translateY(-2px)` lift.
- **Content**: title (2-line clamp), info (4-line clamp), meta (KP/IMDb ratings).

### Buttons
- **Primary**: `{colors.accent}` background, `{colors.accent-ink}` text, `{rounded.m}` radius, `{spacing.2} {spacing.4}` padding.
- **Ghost**: Transparent background, `{colors.ink}` text, `{rounded.m}` radius.
- **Icon**: 40px base, 44px at mobile (`{spacing.tap}`), `{rounded.circle}`.

### Chips & Badges
- **Type badge**: `{colors.accent}` background, `{colors.accent-ink}` text, `{rounded.pill}` radius, `{typography.badge}` type.
- **Rating chip**: Transparent background, colored text (`{colors.kp}` or `{colors.imdb}`), `{rounded.pill}` radius, `{typography.caption}` type, weight 700.
- **Count badge**: `{colors.paper-strong}` background, `{colors.muted}` text, `{rounded.pill}` radius.

### Navigation
- **Inline nav**: Pill links to `#movies`, `#series`, `#documentaries` with count badges. Active state: `{colors.paper-strong}` background.
- **Dialog nav**: Native `<dialog>` below 576px, opened with `showModal()`. Contains duplicate nav links.
- **Breadcrumb**: Home link + type label, `{typography.caption}` type.

### Tables
- **Header**: `{colors.paper}` background, `{typography.caption}` type, weight 500, sortable columns with `aria-sort`.
- **Rows**: Transparent background, 1px `{colors.line}` bottom border, `{typography.body-sm}` type.
- **Title cell**: 32px poster button + title link + alt title + optional fav icon.
- **Column widths**: 34/30/9/13.5/13.5% (desktop), 33/28/12/13.5/13.5% (sm), 45/12/14/14% (xs, genre hidden).

### Film Page Hero
- **Poster**: 240px (mobile) / 320px (desktop) width, `min(100%, 240px)` / `min(320px, 100%)`, height auto.
- **Info**: Badge, meta (year · genres), ratings (KP + IMDb chips), description, share buttons.
- **Share row**: 5-6 social buttons, 40px base / 44px mobile, `{spacing.2}` gap.

## Do's and Don'ts

### Do
- Reserve `{colors.accent}` green ONLY for: brand mark, featured badge, fav icon, focus rings, primary buttons.
- Use hairline borders (1px `{colors.line}`) as the primary depth cue.
- Keep the 96px poster column on every card — the image is a thumbnail, not a hero.
- Use `translateY(-2px)` for card hover lift — no dramatic shadows.
- Set display and headline weights at 700 — never heavier.
- Use `{spacing.tap}` (44px) for all mobile tap targets.
- Keep catalog tables dense but breathable — generous row height, hairline dividers.

### Don't
- Don't introduce a second chromatic accent — the system is green + neutral.
- Don't use heavy drop-shadows on cards — hairline borders are the depth cue.
- Don't make posters larger than 96px on cards — the content is the protagonist.
- Don't use gradients, glassmorphism, or decorative chrome — the content is the design.
- Don't set body text above weight 400 — bold body text breaks the hierarchy.
- Don't use border-radius values outside the 7-token scale.
- Don't add spacing values outside the token scale without tokenizing them first.

## Responsive Behavior

### Breakpoints

| Name | Width | Key Changes |
|---|---|---|
| xs | ≤575px | Burger nav, 4-column tables (genre hidden), featured/related become carousels, 44px tap targets |
| sm | 576–767px | 5-column tables, featured/related 2-column grids |
| md | 768–1023px | Film page poster+info side-by-side, featured/related 2-column grids |
| lg | ≥1024px | Full 4-column featured grid, 5-column tables, 320px film poster |
| xl | ≥1200px | Container caps at 1080px |

### Touch Targets
- All interactive elements ≥44px at mobile (`{spacing.tap}`).
- Buttons use `min-height: var(--tap)` to ensure 44px even when base is 40px.
- Nav links, chips, and icon buttons all meet the 44px floor at xs.

### Collapsing Strategy
- **Nav**: Inline anchors → native `<dialog>` below 576px.
- **Featured grid**: 4-col → 2-col → 1-col (carousel) at xs.
- **Related grid**: auto-fill → 2-col → 1-col (carousel) at xs.
- **Tables**: 5-col → 5-col (adjusted widths) → 4-col (genre hidden) at xs.
- **Film page**: Stacked poster+info → side-by-side at md.

### Image Behavior
- **Posters**: WebP format, 96w/192w/400w variant ladder, `srcset`/`sizes` on hero.
- **Hero**: `sizes="(max-width: 767px) 240px, 320px"` — exact slot declaration.
- **Table posters**: 32px width, no `srcset` (tiny, negligible cost).
- **Lazy loading**: `loading="lazy"` + `decoding="async"` on below-fold images.

## Iteration Guide

1. Focus on ONE component at a time and reference it by its `components:` token name.
2. When introducing a section, decide first which surface lift it lives on.
3. Default body to `{typography.body}` at weight 400.
4. Run `python tools/verify.py` after any CSS change to check token/literal/breakpoint constraints.
5. Treat the green accent as scarce: brand mark, featured badge, fav icon, focus rings, primary buttons.
6. Keep the 96px poster column on every card — the image is a thumbnail, not a hero.

## Known Gaps

- The `.title-primary` uses `overflow-wrap: anywhere` causing mid-word breaks at narrow widths (200 widths in ru, 25 in en) — open product decision.
- The share row wraps at ≤390px with 44px buttons — product decision, not CSS.
- The lightbox has no `srcset`/`sizes` — always loads the 400w or original image.
- 54 of 154 posters exceed the `DISCARDED_AREA_CEILING = 0.02` — gate silenced by human ruling.
- The `.genre-filter` uses bare `height: 44px` instead of `var(--tap)` — no computed effect, left to preserve snapshot evidence.
