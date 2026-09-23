<!-- nnw-theme-stub: agents v1 -->
# Repository guidance

This repository is one NetNewsWire theme: the single root `*.nnwtheme` bundle,
its `fixtures/`, and `screenshots/`. The tooling is the `nnw-theme` npm package;
run it as `npx nnw-theme@1 <command>`. Never install it globally and never add
it to this repository. Read `npx nnw-theme@1 guide` before theme work.

Prefer CSS changes; change
`template.html` only when the requested structure or behavior requires it.
Finish theme work with `npx nnw-theme@1 check` and report the preview path.

Do not change `ThemeIdentifier` or the `.nnwtheme` bundle name after the first
release. Increase the plist `Version` (`npx nnw-theme@1 bump`) before every
release.

If the tooling misbehaves, do not work around it here: report it at
https://github.com/dave-atx/nnw-theme/issues with the `check` version line.

Local edits, renders, checks and packages are safe. Creating a GitHub release,
opening a pull request, changing repository topics, or otherwise mutating
GitHub requires the user's explicit intent. Theme and fixture HTML/JavaScript
are untrusted executable inputs; browser checks stay loopback-only.

## Ember

Ember is a **NetNewsWire article theme**. The shipped product is the bundle in
`Ember.nnwtheme/` — three files:

| File | What it is |
|------|-----------|
| `Ember.nnwtheme/template.html` | The article scaffold. NNW fills `[[macro]]` placeholders (title, byline, dates, avatar, body). It also contains Ember's inline footnote-format adapter; themes cannot load a bundled `.js` file. |
| `Ember.nnwtheme/stylesheet.css` | The whole theme. NNW loads its own `core.css` **first**, then this replaces the default stylesheet. |
| `Ember.nnwtheme/Info.plist` | Theme name, identifier, author, version. |

Everything else is supporting material: `docs/` is the GitHub Pages site
([ember.marquard.org](https://ember.marquard.org), served from the `docs/` folder on
`main`); `fixtures/` holds the test articles.

The tooling is the `nnw-theme` npm package, run as `npx nnw-theme@1 <command>`.
The four workflows, the `creating-nnw-themes` skill, and the guidance above this
section are stubs from
[netnewswire-theme-template](https://github.com/dave-atx/netnewswire-theme-template).
**Fix tooling in [nnw-theme](https://github.com/dave-atx/nnw-theme), never here**, and
keep Ember's own guidance in this section. The skill repeats this file, and
`pages.yml` skips its deploy because Pages serves `docs/` from a branch; both stay
only because `check` warns when a stub is missing.

### How NetNewsWire renders a theme (know this before touching CSS)

A rendered article = a platform **page skeleton** with three macros filled:
`[[title]]`, `[[style]]`, `[[body]]`.

- `[[style]]` = NNW's `core.css` **+** this theme's `stylesheet.css`. Your CSS
  is layered on top of core.css, not instead of it.
- `[[body]]` = `template.html` filled with the article's data.
- Platform differences matter: on **iOS/iPad** `[[font-size]]` is substituted and
  Dynamic Type drives sizing; on **macOS** `[[font-size]]` is left literal and a
  `text_size_class` is set instead. Dark mode is `@media (prefers-color-scheme: dark)`.

`npx nnw-theme@1 guide theme-format` has the details.

### Developing & testing

**Do not eyeball CSS changes.** `npx nnw-theme@1` reproduces NNW's pipeline from
pinned NetNewsWire files and checks every fixture in WebKit, the engine NNW uses.
After `render`, look at `build/preview/` in light and dark on each device and show
the user the change before moving on:

```sh
npx nnw-theme@1 render [fixture ...]   # write build/preview/ once
npx nnw-theme@1 check                  # release gate; finish every change with it
```

`check` renders the package's two built-in fixtures across Mac, iPhone, and iPad, and each
Ember fixture on Mac and iPhone, all in light and dark. It fails on overflow, broken
images, page errors, and footnotes that don't resolve, stay legible, match each
other, or open their popover. `fixtures/footnote-providers.toml` pins the note every
footnote format must open through its `[expect.footnotes]` table, and every footnote
fixture sets `keep_with_word = true` so no marker wraps apart from its word. Real-article
fixtures are captured from NetNewsWire with `npx nnw-theme@1 capture`.

### Conventions

- Fixtures are TOML in `fixtures/` (keys mirror the template variables; HTML bodies
  use `'''triple-quoted'''` literals). Keep interesting edge cases: long byline,
  long title, pull-quotes, figures, footnotes, smart quotes.
- `build/`, `dist/`, and `*.nnwtheme.zip` are build artifacts; never commit them.
- Additional footnote popovers depend on NetNewsWire's **Article JavaScript**
  setting (enabled by default). Keep the adapter inline in `template.html`; `check`
  also renders with theme scripts removed to prove the article still reads well.
- Both light and dark grounds are warm (not a naive inversion); the accent is
  vermilion in light, a lighter coral in dark.
- Commit messages are Conventional Commits; `.github/cliff.toml` turns them into
  the release notes, so the type prefix decides which section a change lands in
  (and `chore(release):` / `ci:` are omitted entirely).

### Releasing

Two version numbers move together, and they are **not** the same number:

| Where | Form | Example |
|-------|------|---------|
| Git tag | `vMAJOR.MINOR` | `v2.2` |
| `Ember.nnwtheme/Info.plist` → `Version` | a plain monotonic **integer**, +1 every release | `8` |

NetNewsWire compares that integer to decide whether an installed theme is
out of date, so it must increase on every release regardless of how the tag
moves. It is *not* derived from the tag.

```sh
npx nnw-theme@1 bump                 # Version +1
git commit -am 'chore(release): v2.2'
git push
```

Then run **Actions → Publish theme** on GitHub with the tag `v2.2`, leaving the notes
empty. Publishing is an external action: confirm with the user first. The workflow
releases the default-branch head after the full check, refuses a reused tag or a
Version that did not increase, attaches `Ember.nnwtheme.zip`, and writes the notes
from the commits since the last tag with git-cliff. Install links on the site and in
the README point at `releases/latest`, and `docs/index.html` reads the current
release from the GitHub API, so nothing else needs editing.
