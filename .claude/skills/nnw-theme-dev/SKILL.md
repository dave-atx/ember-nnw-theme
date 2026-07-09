---
name: nnw-theme-dev
description: Develop and test a NetNewsWire .nnwtheme. Use when working on an .nnwtheme bundle (template.html / stylesheet.css / Info.plist) — reproducing how NetNewsWire renders an article, previewing/screenshotting a theme against captured article fixtures (TOML) across mac/iOS/iPad and light/dark, debugging masthead/typography/layout, or capturing new test cases from a running NetNewsWire.
---

# Developing & testing a NetNewsWire theme

A NetNewsWire theme is a bundle of `template.html`, `stylesheet.css`, and
`Info.plist`. NetNewsWire renders an article by combining the theme with its own
`core.css` and a per-platform page skeleton (see `references/pipeline.md` for the
exact assembly). This skill lets you preview a theme against realistic article
data **without launching NetNewsWire** by reproducing that pipeline faithfully and
screenshotting it in WebKit — the same engine NetNewsWire's `WKWebView` uses.

## Prerequisites

- A local clone of **Ranchero-Software/NetNewsWire** (for `core.css` and the
  `page.html` skeletons). Default location: a sibling `../NetNewsWire` of the
  theme repo, or set `NNW_SRC=/path/to/NetNewsWire`, or pass `--nnw`.
- Python 3.11+ (uses stdlib `tomllib`; no third-party deps).
- Fixtures: `test/*.toml`, each holding one article's template variables.

## The test loop: render → screenshot

1. **Render** a fixture to standalone HTML (auto-detects the theme bundle and the
   NNW checkout):

   ```sh
   python3 .claude/skills/nnw-theme-dev/render.py test/<case>.toml
   # writes test/preview/<case>.mac.html and <case>.ios.html
   ```

   Options: `--platform mac|ios|ipad|all`, `--theme DIR`, `--nnw DIR`,
   `--out DIR`, `--keep-scripts` (leave NNW's `<script>` tags in; off by
   default because they need app message handlers that don't exist in a plain
   browser), `--open` (open the files in a browser).

2. **Screenshot** with the Safari MCP (WebKit = faithful to NNW). Set the
   viewport, then capture:

   | Target | File | Viewport (CSS px) |
   |--------|------|-------------------|
   | iPhone | `<case>.ios.html` | 393 × 852 |
   | iPad   | `<case>.ios.html` | 834 × 1112 |
   | macOS  | `<case>.mac.html` | 1000 × 1200 |

   Use `set_viewport_size` → `navigate_to_url` (a `file://` URL to the rendered
   HTML) → `screenshot`, then Read the PNG. The first `navigate_to_url` auto-
   creates the tab; set the viewport after a tab exists.

3. **Read** the screenshot and compare against the intended design. Iterate on
   `stylesheet.css` / `template.html`, re-render, re-shoot.

### Dark mode

NetNewsWire themes switch on `prefers-color-scheme`. The Safari MCP's
`set_emulated_media` only overrides the media *type* (`screen`/`print`) — it
**cannot** force a color scheme (verified: `matchMedia('(prefers-color-scheme:
dark)')` stays false). So render a dedicated dark file instead:

```sh
python3 .claude/skills/nnw-theme-dev/render.py test/<case>.toml --dark
# writes test/preview/<case>.mac.dark.html and <case>.ios.dark.html
```

`--dark` rewrites the theme's `@media (prefers-color-scheme: dark)` queries so
they always apply (and light ones never do), leaving combined conditions and
nesting intact — engine-independent, so the resulting file previews dark in any
browser. Screenshot it exactly like the light files.

## Capturing new test cases from a running NetNewsWire

Fixtures are just the substitution dictionary NNW builds per article, saved as
TOML. To grab a real one:

1. In your NetNewsWire clone, set a breakpoint on the `return d` line at the end
   of `articleSubstitutions()` in
   `Shared/Article Rendering/ArticleRenderer.swift`.
2. Load the capture command (once per debug session, or add to `~/.lldbinit`).
   Use an **absolute path** — lldb's working directory under Xcode is `/`, so a
   relative import path fails:

   ```
   (lldb) command script import /abs/path/to/.claude/skills/nnw-theme-dev/capture/nnwdump.py
   ```

3. Run the app, select the article you want to capture, and when it stops at the
   breakpoint:

   ```
   (lldb) nnwdump test/<new-case>.toml   # relative -> resolved against repo root
   (lldb) continue
   ```

   (A relative output path is resolved against the repo root, not lldb's `/`
   working directory; absolute paths are honored as-is.)

`nnwdump` writes clean TOML — HTML/multiline values as `'''…'''` literal strings
(no escaping), everything else as `'…'`. It moves values across the debugger
base64-encoded, so nothing is truncated or mis-escaped.

It also resolves the **real feed icon** and embeds it as a `data:image/png`
URL in `avatar_src` (mirroring `ArticleIconSchemeHandler`:
`article.iconImage()?.image.dataRepresentation()`), so previews show the actual
icon rather than render.py's generated placeholder. Pass `--no-icon` to keep the
`nnwImageIcon:` value, or `--article NAME` if the Article value isn't named
`article` in the current frame. If the feed has no icon, the placeholder is kept
automatically. Then render the new fixture as above.

## Writing fixtures by hand

TOML is the fixture format: readable, `tomllib` is stdlib, and `'''triple
literals'''` hold raw HTML bodies with zero escaping. Keys mirror the template
variables (`title`, `byline`, `feed_link_title`, `avatar_src`, `datetime_medium`,
`body`, …; full list in `render.py`'s `TEMPLATE_KEYS` and in the theme's
`template.html` header comment). Any omitted key renders empty. `avatar_src` may
stay `nnwImageIcon:<id>` — render.py swaps it for a generated placeholder tile.
Add `font_size = 17` to override the iOS body size. Good fixtures to keep around:
a long byline, a long title, a pull-quote + figure + captions, footnotes, and
smart quotes / em dashes.

## Fidelity notes

- WebKit renders `-apple-system` fonts faithfully, so type is accurate.
- `<script>`-driven behavior (footnote popovers, image zoom, `processPage()`) is
  **not** exercised by default — this loop is for CSS/layout/typography. Use
  `--keep-scripts` only to inspect the markup they'd act on.
- render.py injects `<meta charset="utf-8">` (NNW's `loadHTMLString` defaults to
  UTF-8; a bare `file://` would otherwise mangle smart quotes).
- See `references/pipeline.md` for the authoritative assembly order and the exact
  macOS-vs-iOS differences (`font-size`, `text_size_class`, scripts).
