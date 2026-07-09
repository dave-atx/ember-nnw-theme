# How NetNewsWire renders an article (the pipeline render.py reproduces)

Source of truth: a clone of [Ranchero-Software/NetNewsWire](https://github.com/Ranchero-Software/NetNewsWire).
NNW's own theme-authoring guide is `Technotes/Themes.md` in that repo.
Key files (paths relative to the NNW repo root):

| File | Role |
|------|------|
| `Shared/Article Rendering/ArticleRenderer.swift` | Builds the substitution dictionaries. `articleSubstitutions()` → the article data; `styleSubstitutions()` → the style macros. Runs the **first** MacroProcessor pass (template.html + theme CSS). |
| `Shared/Article Rendering/core.css` | Structural CSS NNW always prepends, *before* the theme. Ad-blocking rules, footnote/newsfoot layout, `scrollbar-gutter`, activity indicator. |
| `Shared/ArticleStyles/ArticleTheme.swift` | Assembles `css = core.css + "\n" + <theme>/stylesheet.css` and loads `<theme>/template.html`. |
| `Shared/Article Rendering/WebViewConfiguration.swift` | Injects the article JS and the content-blocking rule list into the web view (see "Scripts", below). |
| `Shared/Article Rendering/ArticleRenderingSpecialCases.swift` | Site-specific final-HTML fixup (see "Other layers", below). |
| `Mac/MainWindow/Detail/DetailWebViewController.swift` / `iOS/Article/WebViewController.swift` | Run the **second** MacroProcessor pass (drop the rendered tuple into `page.html`) and `loadHTMLString`. |
| `Mac/MainWindow/Detail/page.html` | macOS page skeleton. Bare — no `<script>` tags, no viewport meta. JS still runs (injected by the app, not the page). |
| `iOS/Resources/page.html` | iOS/iPadOS page skeleton. Has the viewport meta and lists `main.js`/`main_ios.js`/`newsfoot.js` plus a `processPage()` call — but the effective JS is injected by the app the same way as on Mac. |
| `RSCore` `MacroProcessor` | Does the `[[key]]` substitution. |

## Assembly order

The document is built in **two MacroProcessor passes**, not one:

**Pass 1 — in `ArticleRenderer`** — produces a `(style, html, title, baseURL)` tuple:

1. **Style** = `core.css` + `"\n"` + theme `stylesheet.css`, then macro-substituted
   by `styleSubstitutions()`:
   - **iOS/iPad**: `[[font-size]]` → `UIFont.preferredFont(forTextStyle: .body).pointSize`
     (17pt at the default Dynamic Type size).
   - **macOS**: `styleSubstitutions()` returns an empty dict, so `[[font-size]]` is
     **left literal** — those CSS rules are invalid and dropped by WebKit. Themes
     therefore keep `[[font-size]]` inside `@media`/`@supports` blocks that only apply on iOS.

2. **Body** = theme `template.html`, macro-substituted by `articleSubstitutions()`
   (title, byline, dates, `avatar_src`, `dateline_style`, `body`, …).
   - `text_size_class` is set **only on macOS** (`smallText`…`xxLargeText`). On iOS
     it is absent and Dynamic Type drives size via `:root { font-size }`.
   - `dateline_style` = `articleDatelineTitle` when the title is empty, else
     `articleDateline`.
   - `avatar_src` uses the app-internal `nnwImageIcon:<articleID>` scheme, which
     only resolves inside the app. render.py swaps it for a generated placeholder
     (or `nnwdump` embeds the real feed icon as a `data:` URL at capture time).

**Pass 2 — in the platform web-view controller** — `MacroProcessor` fills the
platform `page.html` skeleton with `[[title]]`, `[[style]]`, `[[body]]`, and
(iOS) `[[baseURL]]` / `[[windowScrollY]]` from the pass-1 tuple. The result is
then run through the site-specific fixup below and handed to `loadHTMLString`.

## MacroProcessor semantics (must match exactly)

- Delimiters `[[` … `]]`.
- **Single pass, non-recursive**: a value that itself contains `[[x]]` is not
  re-expanded (verified by `MacroProcessorTests.testMacroInSubstitutions`).
  (This is per pass — the two passes above are two separate, independent runs.)
- **Unknown key → left literal**: `[[nonexistent]]` stays in the output verbatim
  (`MacroProcessorTests` "Nonexistent key" case). render.py implements this with a
  single `re.sub` whose replacement returns the original match when the key is
  unknown — and it never re-scans substituted text.

## Scripts — main.js / newsfoot.js run on **both** platforms

The scripts are **not** iOS-only, and are not driven by `page.html`'s `<script>`
tags. `WebViewConfiguration.articleScripts` builds
`["main", "main_ios"|"main_mac", "newsfoot"]` (platform-selected via `#if os(iOS)`)
and adds each as a `WKUserScript(injectionTime: .atDocumentStart, forMainFrameOnly: true)`
to the web view's `userContentController`. So the JS arrives from the *app*, for
both Mac and iOS. macOS's `page.html` has no `<script>` tags precisely because it
doesn't need them — the app injects the JS regardless.

`main.js` self-invokes `processPage()` from its own `DOMContentLoaded` listener
(independent of the inline `processPage()` call written into iOS's `page.html`).
`processPage()` runs, on **both platforms**:

- `stripStyles()` — deletes inline `color`, `background`, `font`, `max-width`,
  `max-height`, `position` off every `[style]` element in the body.
- `wrapFrames()`, `constrainBodyRelativeIframes()`, `wrapTables()`,
  `inlineVideos()`, `flattenPreElements()` — structural wrapping.
- `convertImgSrc()` — resolves relative `img` `src`s to absolute against the base
  URL (or uses `data-canonical-src`). Benign for normal absolute URLs.
- `styleLocalFootnotes()` — adds the `.footnote` class to inline `<sup><a href="#fn…">`
  markers. **This is what turns a footnote reference into a badge** (core.css / the
  theme style `a.footnote`); it is applied at runtime, not present in the static HTML.
- `removeWpSmiley()`.

`newsfoot.js` then turns `.footnote` clicks into inline popovers.

Only a few things are genuinely native-only and do nothing in a plain browser:
`main_mac.js` / `main_ios.js`'s `postRenderProcessing()` scroll/hover reporting via
`window.webkit.messageHandlers.*`, and iOS image-click-to-zoom. A theme author
never needs to see those.

## Other layers (not theme-controllable, but they shape the final DOM)

- **Content blocking (two layers).** core.css carries CSS `display:none` ad/tracker
  rules, *and* `WebViewConfiguration` compiles `Shared/Resources/ContentRules.json`
  into a `WKContentRuleList` attached to the web view — a second, broader
  network/element blocking layer.
- **Site-specific mojibake fixup.** After pass 2, before `loadHTMLString`, both
  controllers call `ArticleRenderingSpecialCases.filterHTMLIfNeeded(baseURL:html:)`.
  Today it only fires for `theverge.com` hosts (`filterVergeHTML` — reverses common
  UTF-8-as-Latin-1 mojibake). Not theme-controllable, but it means the true final
  HTML can differ slightly from raw MacroProcessor output for those sites.
- **Dead-code caveat (do not "fix").** `ArticleRenderer.defaultStyleSheet` (theme
  CSS *without* core.css) looks like a gap but is unreachable in practice: a valid
  theme's stylesheet is always prepended with core.css; the fallback only fires for
  a broken custom theme missing its `stylesheet.css`.

## How render.py maps onto this

render.py reproduces both passes: it builds the style + body (pass 1 semantics),
substitutes them into the platform skeleton (pass 2), and — by default — injects
and runs `main.js` + the platform script + `newsfoot.js` before `</body>`, with a
tiny `window.webkit.messageHandlers` Proxy shim so the native-only calls no-op
instead of throwing. That reproduces the post-`processPage()` DOM (style stripping,
table/iframe wrapping, footnote badges + popovers) on both platforms. Pass
`--no-scripts` to skip injection and inspect the raw pass-2 macro output instead.
It does **not** reproduce the ContentRules network blocking or the Verge fixup
(neither is theme-relevant).

## Fidelity caveats

- render.py's script shim is not a full app environment: the native message-handler
  round-trips (scroll/hover reporting, iOS image zoom) are stubbed to no-ops. The
  DOM-mutating parts of `processPage()` — the parts a theme author cares about — do
  run.
- Fonts: WebKit uses the real `-apple-system` stack, so type is faithful on macOS.
- The most faithful engine to screenshot in is WebKit itself (NNW uses WKWebView) —
  the Safari MCP is exactly that engine.
