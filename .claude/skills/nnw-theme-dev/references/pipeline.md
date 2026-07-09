# How NetNewsWire renders an article (the pipeline render.py reproduces)

Source of truth: a clone of [Ranchero-Software/NetNewsWire](https://github.com/Ranchero-Software/NetNewsWire).
NNW's own theme-authoring guide is `Technotes/Themes.md` in that repo.
Key files (paths relative to the NNW repo root):

| File | Role |
|------|------|
| `Shared/Article Rendering/ArticleRenderer.swift` | Builds the substitution dictionaries. `articleSubstitutions()` → the article data; `styleSubstitutions()` → the style macros. |
| `Shared/Article Rendering/core.css` | Structural CSS NNW always prepends, *before* the theme. Ad-blocking rules, footnote/newsfoot layout, `scrollbar-gutter`, activity indicator. |
| `Shared/ArticleStyles/ArticleTheme.swift` | Assembles `css = core.css + "\n" + <theme>/stylesheet.css` and loads `<theme>/template.html`. |
| `iOS/Resources/page.html` | iOS/iPadOS page skeleton. Has the viewport meta, `main.js`/`main_ios.js`/`newsfoot.js`, and a `processPage()` call. |
| `Mac/MainWindow/Detail/page.html` | macOS page skeleton. Bare — no scripts, no viewport meta. |
| `RSCore` `MacroProcessor` | Does the `[[key]]` substitution. |

## Assembly order

1. **Style** = `core.css` + `"\n"` + theme `stylesheet.css`, then macro-substituted
   by `styleSubstitutions()`:
   - **iOS/iPad**: `[[font-size]]` → `UIFont.preferredFont(forTextStyle: .body).pointSize`
     (17pt at the default Dynamic Type size).
   - **macOS**: `styleSubstitutions()` returns an empty dict, so `[[font-size]]` is
     **left literal** — those CSS rules are invalid and dropped by WebKit. Themes
     therefore keep `[[font-size]]` inside `@media` blocks that only apply on iOS.

2. **Body** = theme `template.html`, macro-substituted by `articleSubstitutions()`
   (title, byline, dates, `avatar_src`, `dateline_style`, `body`, …).
   - `text_size_class` is set **only on macOS** (`smallText`…`xxLargeText`). On iOS
     it is absent and Dynamic Type drives size via `:root { font-size }`.
   - `dateline_style` = `articleDatelineTitle` when the title is empty, else
     `articleDateline`.
   - `avatar_src` uses the app-internal `nnwImageIcon:<articleID>` scheme, which
     only resolves inside the app. render.py swaps it for a generated placeholder.

3. **Page** = the platform skeleton with `[[title]]`, `[[style]]`, `[[body]]`,
   and (iOS) `[[baseURL]]` / `[[windowScrollY]]` filled in.

## MacroProcessor semantics (must match exactly)

- Delimiters `[[` … `]]`.
- **Single pass, non-recursive**: a value that itself contains `[[x]]` is not
  re-expanded (verified by `MacroProcessorTests.testMacroInSubstitutions`).
- **Unknown key → left literal**: `[[nonexistent]]` stays in the output verbatim
  (`MacroProcessorTests` "Nonexistent key" case). render.py implements this with a
  single `re.sub` whose replacement returns the original match when the key is
  unknown — and it never re-scans substituted text.

## Fidelity caveats

- render.py strips `<script>` tags by default (NNW's JS expects app message
  handlers that don't exist in a plain browser). So JS-driven behavior — footnote
  popovers (`newsfoot.js`), image zoom, `processPage()` transforms — is **not**
  exercised. Pass `--keep-scripts` if you need to inspect them, but expect console
  errors. Masthead/typography/layout — the common theme concerns — render faithfully.
- Fonts: WebKit uses the real `-apple-system` stack, so type is faithful on macOS.
- The most faithful engine to screenshot in is WebKit itself (NNW uses WKWebView) —
  the Safari MCP is exactly that engine.
