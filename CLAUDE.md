# Ember — NetNewsWire theme (agent & contributor orientation)

Ember is a **NetNewsWire article theme**. The shipped product is the bundle in
`Ember.nnwtheme/` — three files:

| File | What it is |
|------|-----------|
| `Ember.nnwtheme/template.html` | The article scaffold. NNW fills `[[macro]]` placeholders (title, byline, dates, avatar, body). |
| `Ember.nnwtheme/stylesheet.css` | The whole theme. NNW loads its own `core.css` **first**, then this replaces the default stylesheet. |
| `Ember.nnwtheme/Info.plist` | Theme name, identifier, author, version. |

Everything else is supporting material: `docs/` is the GitHub Pages site
([ember.marquard.org](https://ember.marquard.org)); `test/` holds article
fixtures; `preview.html` / `section-heads.html` are gitignored local artifacts.

## How NetNewsWire renders a theme (know this before touching CSS)

A rendered article = a platform **page skeleton** with three macros filled:
`[[title]]`, `[[style]]`, `[[body]]`.

- `[[style]]` = NNW's `core.css` **+** this theme's `stylesheet.css`. Your CSS
  is layered on top of core.css, not instead of it.
- `[[body]]` = `template.html` filled with the article's data.
- Platform differences matter: on **iOS/iPad** `[[font-size]]` is substituted and
  Dynamic Type drives sizing; on **macOS** `[[font-size]]` is left literal and a
  `text_size_class` is set instead. Dark mode is `@media (prefers-color-scheme: dark)`.

Full details, with file paths into a NetNewsWire checkout, are in
`.claude/skills/nnw-theme-dev/references/pipeline.md`.

## Developing & testing — use the `nnw-theme-dev` skill

**Do not eyeball CSS changes.** Preview them against real article data by
reproducing NNW's exact pipeline and screenshotting in WebKit (the same engine
NNW uses). The workflow lives in the **`nnw-theme-dev` skill**
(`.claude/skills/nnw-theme-dev/`); load it for any theme work. In short:

```sh
# Render a fixture to faithful per-platform HTML (auto-detects the bundle + NNW):
python3 .claude/skills/nnw-theme-dev/render.py test/<case>.toml            # light
python3 .claude/skills/nnw-theme-dev/render.py test/<case>.toml --dark      # dark
# -> test/preview/<case>.{mac,ios}[.dark].html
```

Then screenshot with the Safari MCP at iPhone 393×852, iPad 834×1112, macOS
1000×1200 (or just open the files in a browser). **macOS + Python 3.11+**, and a
**NetNewsWire clone** for `core.css` + page skeletons (default `../NetNewsWire`,
override with `NNW_SRC` or `--nnw`). Full requirements are in the skill's
`SKILL.md`.

Capture new fixtures from a running NetNewsWire with the `nnwdump` lldb command
(see the skill) — it writes clean TOML and embeds the real feed icon.

## Conventions

- Fixtures are TOML in `test/` (keys mirror the template variables; HTML bodies
  use `'''triple-quoted'''` literals). Keep interesting edge cases: long byline,
  long title, pull-quotes, figures, footnotes, smart quotes.
- `test/preview/`, `preview.html`, `section-heads.html`, and
  `Ember.nnwtheme.zip` are build artifacts — gitignored, never commit them.
- Releases are tag-driven: pushing a `v*` tag builds the zip and publishes a
  GitHub Release (`.github/workflows/release.yml`). Install links point at
  `releases/latest`.
- Both light and dark grounds are warm (not a naive inversion); the accent is
  vermilion in light, a lighter coral in dark.
