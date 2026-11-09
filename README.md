<!-- nnw-theme-identity:start -->
# Ember — a NetNewsWire theme

A warm, editorial theme for [NetNewsWire](https://netnewswire.com) using Apple system
fonts with a vermilion accent, big headline type, a drop cap, serif-italic captions,
and full-bleed images. Designed for **macOS, iOS, and iPadOS**, with first-class light
and dark modes.

**→ [ember.marquard.org](https://ember.marquard.org)**

<p align="center">
  <img src="screenshots/theme-preview.png" width="720" alt="An article in Ember, split diagonally between light and dark mode: a bold headline, vermilion dateline, drop cap, and a photo of a Martian landscape">
</p>

## Install

**One click.** On your Mac, iPhone, or iPad, open **[ember.marquard.org](https://ember.marquard.org)**
and tap **Install in NetNewsWire**. NetNewsWire opens and offers to add Ember.

> The install button uses NetNewsWire's `netnewswire://theme/add` URL scheme. GitHub
> strips custom-scheme links from rendered Markdown, so the working button lives on the
> site rather than in this README.

**Manually.** Download the latest [`Ember.nnwtheme.zip`](https://github.com/dave-atx/ember-nnw-theme/releases/latest):

- **macOS** — unzip and double-click `Ember.nnwtheme`; confirm the install.
- **iOS / iPadOS** — open the `.zip` and share it to NetNewsWire.

Then choose **Ember** as your article theme in NetNewsWire's settings.

## Features

- **Apple system fonts** (SF Pro) throughout — nothing to download, crisp at every size.
- **Warm vermilion accent** that shifts to a lighter coral in dark mode for legibility.
- **Drop cap** on the opening paragraph and a confident headline scale.
- **Flagged section headings** — a short accent bar marks each `<h2>`/`<h3>`.
- **Prominent pull-quotes** with a tinted panel and accent rule.
- **Full-bleed images** that span the column edge-to-edge, captions kept inset.
- **Captions set apart** in serif italic, with photo credits in muted small caps.
- **Podcasts, video, and photos** — an article's enclosures get a design of their own:
  audio as a card with the episode's title, length, and size; video players and
  episode artwork leading the article; attached photos as a gallery after it.
- **Broader footnote support** with native-style popovers for common Markdown,
  Substack, and WordPress footnote formats.
- **Designed light and dark** — both grounds are warm, not a naive inversion.
- **Platform-tuned** — Dynamic Type on iOS, a larger default size on iPad, and a
  desktop type scale on macOS.

## Requirements

A recent version of NetNewsWire (which supports custom `.nnwtheme` themes) on macOS,
iOS, or iPadOS.

Enclosures (podcast audio, video, and attached images) need NetNewsWire 7.3, in beta
as of November 2026. Earlier releases don't show enclosures at all, and Ember reads as
before there. Splitting the audio card's title from its details also takes Article
JavaScript; without it, the whole caption heads the card.

Ember's additional footnote formats require NetNewsWire's **Article JavaScript**
setting, which is enabled by default. If it is disabled, Ember still renders normally,
but only the footnote formats recognized directly by that NetNewsWire version receive
interactive popovers.

## Structure

An `.nnwtheme` bundle is three files. NetNewsWire always loads its own `core.css`
first, then a theme's `stylesheet.css` (which fully replaces the default stylesheet).

```
Ember.nnwtheme/
├── Info.plist       theme name, identifier, author, version
├── template.html    the article scaffold, plus the inline footnote adapter
└── stylesheet.css   the theme (self-contained; replaces the default)
```

The `docs/` folder is the [project site](https://ember.marquard.org) served via GitHub
Pages.

## Developing & testing

Ember uses [nnw-theme](https://github.com/dave-atx/nnw-theme), the tooling behind
[netnewswire-theme-template](https://github.com/dave-atx/netnewswire-theme-template):
it renders each article through NetNewsWire's own pipeline (its pinned `core.css`,
page skeletons, and scripts) and checks the result in WebKit, so layout work needs
neither the app nor a NetNewsWire checkout.

**Requirements:** Node.js 24 or later (`brew install node` on macOS). Capturing new
fixtures from the running app additionally needs Xcode and a NetNewsWire clone.

```sh
npx nnw-theme@2 setup      # once: install WebKit
npx nnw-theme@2 preview    # live gallery of every fixture; rebuilds on save
npx nnw-theme@2 check      # release gate: every fixture in WebKit, light and dark
```

Test cases are TOML fixtures in `fixtures/` whose keys mirror the `[[variables]]` in
`template.html`; the tool's built-in `article` and `kitchen-sink` fixtures render
alongside them. `npx nnw-theme@2 capture` explains how to save a real article from
NetNewsWire as a new one. `footnote-providers.toml` declares the note each footnote
format must open, which `check` verifies. Contributor and agent orientation lives in
[`AGENTS.md`](AGENTS.md).

`npx nnw-theme@2` picks up new 2.x tooling releases on its own; there is nothing to
update in this repository.

## Releasing

1. Run `npx nnw-theme@2 bump` and commit the new `Info.plist` version.
2. In GitHub, run **Actions → Publish theme** with the new tag (for example, `v2.3`).

The workflow checks the theme, refuses a reused tag or a version that did not
increase, attaches `Ember.nnwtheme.zip`, and writes the release notes from the commits
since the last tag with [git-cliff](https://git-cliff.org). The install links always
point at `releases/latest`, so they pick up the newest release automatically.

## License

[Apache License 2.0](LICENSE) © 2026 Dave Marquard.
<!-- nnw-theme-identity:end -->
