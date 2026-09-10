---
name: nnw-theme-dev
description: Develop and test a NetNewsWire .nnwtheme (macOS only). Use when working on an .nnwtheme bundle (template.html / stylesheet.css / Info.plist) — reproducing how NetNewsWire renders an article, previewing/screenshotting a theme against captured article fixtures (TOML) across mac/iOS/iPad and light/dark, debugging masthead/typography/layout, or capturing new test cases from a running NetNewsWire.
---

# Developing & testing a NetNewsWire theme

A NetNewsWire theme is a bundle of `template.html`, `stylesheet.css`, and
`Info.plist`. NetNewsWire renders an article by combining the theme with its own
`core.css` and a per-platform page skeleton (see `references/pipeline.md` for the
exact assembly). This skill lets you preview a theme against realistic article
data **without launching NetNewsWire** by reproducing that pipeline faithfully and
screenshotting it in WebKit — the same engine NetNewsWire's `WKWebView` uses.

## Requirements

**macOS only** — WebKit rendering and Apple system fonts are what make the
preview faithful; capturing fixtures additionally needs Xcode.

**To render & preview (the core loop):**

- **Python 3.11+** — stdlib `tomllib`, no third-party deps. macOS doesn't ship
  `python3`; install Xcode Command Line Tools (`xcode-select --install`) or
  Homebrew. Verify with `python3 --version`.
- **A NetNewsWire source checkout** — supplies `core.css` and the `page.html`
  skeletons. The *source files* are enough; no build needed. Default location: a
  sibling `../NetNewsWire`; or set `NNW_SRC=/path/to/NetNewsWire`, or pass
  `--nnw`. Clone with
  `git clone https://github.com/Ranchero-Software/NetNewsWire`. (NNW's own theme
  format is documented in its `Technotes/Themes.md`.)
- **A way to view the rendered HTML:**
  - *Humans* — open the files in Safari or any browser (`render.py --open`).
  - *Agents* — a WebKit-screenshot MCP. This repo uses the **Safari Technology
    Preview MCP**, which needs Apple's free **Safari Technology Preview** app
    installed. render.py just emits standalone HTML, so any equivalent
    browser-automation MCP works too.

**To capture new fixtures (optional — see below):**

- **Xcode** plus a *buildable* NetNewsWire checkout, to run the app under the
  debugger. Follow NetNewsWire's build instructions (its repo `README` /
  `CONTRIBUTING.md`).

Fixtures live in `test/*.toml`, each holding one article's template variables.

## The test loop: render → screenshot

1. **Render** a fixture to standalone HTML (auto-detects the theme bundle and the
   NNW checkout):

   ```sh
   python3 .claude/skills/nnw-theme-dev/render.py test/<case>.toml
   # writes test/preview/<case>.mac.html and <case>.ios.html
   ```

   Options: `--platform mac|ios|ipad|all`, `--theme DIR`, `--nnw DIR`,
   `--out DIR`, `--dark` (see below), `--no-scripts` (see "Fidelity notes"),
   `--open` (open the files in a browser).

2. **View / screenshot.** Humans can just open the file (`--open`). Agents
   screenshot it with a WebKit MCP (WebKit = faithful to NNW) — this repo uses
   the Safari Technology Preview MCP. Set the viewport, then capture:

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

### Checking the footnote adapter

`test/footnote-providers.toml` exercises every footnote format the inline adapter
in `template.html` normalizes. `check_footnotes.js` asserts the result instead of
leaving it to the eye — each provider is recognized, its note resolves to the
right text, the popover opens, no ids are duplicated, and every marker's numeral
is legible inside its capsule (the check that catches a platform `body a *` rule
repainting a nested `<sup>` accent-on-accent).

It also asserts that every marker *presents identically* — same height, seat,
font-size, an oblong rather than circular capsule, a bare numeral, and no space
between the marker and the word it annotates. Providers disagree about whether a
reference is wrapped in `<sup>`, and while that wrapper owned the sizing and the
raise, two markers in one sentence could differ by 20% in size and 4px in height.
Seat is measured against a probe glyph on the marker's own line, so it stays
meaningful in real prose where markers land on different lines.

The same geometry is re-measured *after* the popover opens. On first click
newsfoot moves the anchor into a `.newsfoot-footnote-container` it inserts in the
anchor's place, which silently takes the marker out from under any rule keyed on
its original parent — that is how a `sup:has(> a.footnote)` rule let markers
shrink the moment you tapped them.

The check is **fixture-agnostic** — only the provider-by-provider expectations
are specific to `footnote-providers.toml` (it detects that fixture by its
negative control), so run it against real captured articles too.
`test/sixcolors-footnotes.toml` is one: Six Colors wraps every marker in a
`<sup>` and emits absolute `https://sixcolors.com#fn-…` hrefs with unclassed
`↩` return links, which exercises the adapter's absolute-backlink rewriting on
markup nobody wrote for us.

```sh
for f in footnote-providers sixcolors-footnotes; do
  python3 .claude/skills/nnw-theme-dev/render.py test/$f.toml --platform all
  python3 .claude/skills/nnw-theme-dev/render.py test/$f.toml --platform all --dark
done
```

Then, for **each of the four renders** of each fixture, evaluate the contents of
`check_footnotes.js` in the page — agents via the Safari MCP's
`evaluate_javascript`, humans by pasting into the browser console. It returns
`{pass, failed, total, failures}`; all must pass. Run all four platform/scheme
combinations: the legibility assertions can only fail in the scheme and platform
they run in.

**Keep the browser window frontmost while it runs.** The popover assertions wait
on `setTimeout`, and a backgrounded tab throttles those hard enough (seconds per
tick) that the run looks hung and the MCP call times out.

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

   To load it automatically, add that line to `~/.lldbinit` — but note **Xcode
   ignores `~/.lldbinit` unless you enable *"Load system and user startup
   files"*** (Xcode ▸ Settings ▸ Components, or
   `defaults write com.apple.dt.Xcode IDEDebuggerFeatureSetting -int 12`). A
   project-local `.lldbinit` is also honored with that setting on.

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
- **NNW's article JS runs by default, on both platforms.** NetNewsWire injects
  `main.js` + the platform script + `newsfoot.js` as `WKUserScript`s (not via
  `page.html`), so `processPage()` runs on Mac *and* iOS — inline-style stripping,
  table/iframe wrapping, image-src resolution, footnote badges (`styleLocalFootnotes()`
  adds `.footnote` at runtime) and newsfoot popovers. render.py reproduces this,
  with a `window.webkit.messageHandlers` shim so the native-only scroll/hover/zoom
  calls no-op instead of throwing. Pass `--no-scripts` to skip it and inspect the
  raw macro output (smaller, un-transformed HTML) — useful when a bug might live in
  the template itself rather than after the JS runs.
- Inline scripts supplied by a theme are preserved in normal previews and removed
  by `--no-scripts`. In NetNewsWire they require the user-facing **Article
  JavaScript** setting, which is enabled by default.
- render.py injects `<meta charset="utf-8">` (NNW's `loadHTMLString` defaults to
  UTF-8; a bare `file://` would otherwise mangle smart quotes).
- Not reproduced (not theme-relevant): the `ContentRules.json` network blocking
  layer and the `theverge.com`-only mojibake fixup — both described in
  `references/pipeline.md`.
- See `references/pipeline.md` for the authoritative two-pass assembly order and
  the exact macOS-vs-iOS differences (`font-size`, `text_size_class`, scripts).
