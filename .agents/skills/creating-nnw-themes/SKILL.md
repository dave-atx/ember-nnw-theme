---
name: creating-nnw-themes
description: Create, restyle, preview, test, package, or publish the NetNewsWire theme in this repository. Do not use for generic web design or NetNewsWire app development.
---

# Create NetNewsWire themes

The upstream repository is a GitHub template. Work in the person's own repository made via
**Use this template**, not in the upstream template or a fork. If they already have
their own copy open, use it. Otherwise, help them create one from
`dave-atx/netnewswire-theme-template` if you can, or ask them to create and open it;
confirm before creating a GitHub repository. Then work on its single root-level
`*.nnwtheme` bundle. If `.nnw-theme-uninitialized` exists, run the guided
`uv run nnw-theme init` before design work; let the person approve the permanent
identifier even when other identity details are already known.

Collect or infer a compact design brief: mood, typography, color direction, and any
specific reading needs. Prefer changing the CSS variables and rules in
`stylesheet.css`. Edit `template.html` only when the requested structure or behavior
needs it. For format constraints and macro behavior, read
[references/theme-format.md](references/theme-format.md). To preview content the
starter articles lack, such as a real feed's markup or footnotes, add a fixture as
described in [references/fixtures.md](references/fixtures.md).

Iterate with this loop:

1. Make a focused theme edit.
2. Run `uv run nnw-theme render` for fast generated pages or
   `uv run nnw-theme screenshot` when a checked image is needed.
3. Inspect relevant light/dark and device previews under `build/preview/`.
4. Explain what changed in visual terms and incorporate the person’s reaction.

Use [references/design-checklist.md](references/design-checklist.md) during final
visual review. Always finish implementation with `uv run nnw-theme check`; do not
substitute a Chromium result for the required WebKit gate. Give the person a concrete
preview or screenshot path they can open.

Treat the root bundle filename and `ThemeIdentifier` as permanent after the first
release. Increase the integer `Version` with `uv run nnw-theme bump` for each release.
Read [references/publishing.md](references/publishing.md) for publishing work. Local
packaging is not publication. Obtain clear user confirmation immediately before
triggering a GitHub release or another external mutation.
