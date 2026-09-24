---
name: creating-nnw-themes
description: Create, restyle, preview, test, package, or publish the NetNewsWire theme in this repository. Do not use for generic web design or NetNewsWire app development.
---
<!-- nnw-theme-stub: skill v2 -->

# Create NetNewsWire themes

Read the full guide first: `npx nnw-theme@2 guide`. Details live in its topics
(`npx nnw-theme@2 guide theme-format`, `fixtures`, `design-checklist`, `publishing`),
which update with the tool.

1. If `.nnw-theme-uninitialized` exists, run `npx nnw-theme@2 init` and let the person
   approve the permanent theme identifier.
2. Collect a compact design brief: mood, typography, color, reading needs.
3. Edit `stylesheet.css` first; change `template.html` only when structure requires it.
4. Run `npx nnw-theme@2 render` and inspect `build/preview/` in light and dark on each
   device; explain the change and take the person's reaction.
5. Finish with `npx nnw-theme@2 check` and give the person the preview path.

Never change the bundle name or `ThemeIdentifier` after the first release. Confirm
with the person immediately before any release or other GitHub mutation.
