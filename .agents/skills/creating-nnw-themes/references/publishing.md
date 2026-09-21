# Publishing and marketplace listing

Read this before versioning, promoting the marketplace screenshot, changing GitHub
metadata, or releasing.

Run `uv run nnw-theme bump`, commit the new integer `Version`, and run
`uv run nnw-theme check`. The bundle filename and `ThemeIdentifier` cannot change
after the first release. Release tags may use any valid Git ref beginning with `v`;
semantic tags such as `v1.0.0` are the suggested default and are independent of the
plist version.

Publishing is manual: use **Actions → Publish theme → Run workflow** or an equivalent
explicitly authorized GitHub CLI action. Tag pushes do not publish. The workflow uses
the current default-branch HEAD, refuses an existing tag/release, compares identity
and version to the previous stable release, and uploads one
`<Name>.nnwtheme.zip` asset. Notes are optional; when they are empty and
`.github/cliff.toml` exists, git-cliff generates them from the commits since the
previous tag.

Marketplace participation is optional. Automatic discovery expects a public,
non-archived, non-fork repository; the `netnewswire-theme` or `netnewswire` topic; a
stable GitHub release; and the valid ZIP asset. A useful repository description and
`screenshots/theme-preview.png` improve the card. Missing optional marketplace/card
metadata warns but does not block publication. `uv run nnw-theme marketplace enable`
adds the recommended topic through the author’s authenticated `gh` session.

Creating releases, topics, branches, pull requests, or other GitHub state is external
mutation. Confirm the person’s intent immediately before doing it. Ordinary edits,
local previews, checks, and packages do not need that additional confirmation.
