# Ember — a NetNewsWire theme

A warm, editorial theme for [NetNewsWire](https://netnewswire.com) using Apple system
fonts with a vermilion accent, big headline type, a drop cap, flagged section headings,
and full-bleed images. Designed for **macOS, iOS, and iPadOS**, with first-class light
and dark modes.

**→ [ember.marquard.org](https://ember.marquard.org)**

<p align="center">
  <img src="docs/assets/ember-macos-light.png" width="46%" alt="Ember on macOS, light mode">
  <img src="docs/assets/ember-macos-dark.png" width="46%" alt="Ember on macOS, dark mode">
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
- **Designed light and dark** — both grounds are warm, not a naive inversion.
- **Platform-tuned** — Dynamic Type on iOS, a larger default size on iPad, and a
  desktop type scale on macOS.

## Requirements

A recent version of NetNewsWire (which supports custom `.nnwtheme` themes) on macOS,
iOS, or iPadOS.

## Structure

An `.nnwtheme` bundle is three files. NetNewsWire always loads its own `core.css`
first, then a theme's `stylesheet.css` (which fully replaces the default stylesheet).

```
Ember.nnwtheme/
├── Info.plist       theme name, identifier, author, version
├── template.html    the article scaffold NetNewsWire fills in
└── stylesheet.css   the theme (self-contained; replaces the default)
```

The `docs/` folder is the [project site](https://ember.marquard.org) served via GitHub
Pages.

## Releasing

Pushing a `v*` tag builds `Ember.nnwtheme.zip` and publishes a GitHub Release with the
zip attached (see [`.github/workflows/release.yml`](.github/workflows/release.yml)). The
install links always point at `releases/latest`, so they pick up the newest release
automatically.

```sh
git tag v1.0 && git push origin v1.0
```

## License

[Apache License 2.0](LICENSE) © 2026 Dave Marquard.
