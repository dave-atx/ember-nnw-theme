# Repository guidance

The upstream repository `dave-atx/netnewswire-theme-template` is a GitHub template
for creating one NetNewsWire theme per derived repository. If asked to start a new
theme, use an existing repository created via
**Use this template** or help the user create their own repository from
`dave-atx/netnewswire-theme-template`; do not fork or initialize the upstream
template repository. If you cannot create the repository, ask the user to do so and
open their copy before editing. Do not assume a local clone of the template is a
new theme repository. Confirm with the user before creating a GitHub repository.

In the user's theme repository, run `uv run nnw-theme init` if
`.nnw-theme-uninitialized` exists; let the user confirm the permanent theme
identifier. Prefer CSS changes; change `template.html` only when the requested
structure or behavior requires it. In a theme repository, fix tooling upstream rather
than locally: `uv run nnw-theme update` replaces it. Run `update` only when the user
asks, and commit its changes separately from theme changes.

Use `uv` for every Python command and Python 3.14. After changing Python, run:

```sh
uv run ruff check --fix .
uv run ruff format .
uv run ruff check .
uv run ruff format --check .
uv run python -m unittest discover -s tests -v
```

Use the installed `playwright-cli` through `uv run nnw-theme`; never use `npx` for
local browser validation. Finish theme work with `uv run nnw-theme check` and report
the preview path. Do not change `ThemeIdentifier` or the `.nnwtheme` bundle name after
the first release. Increase the plist `Version` before every release.

Local edits, renders, checks, and packages are safe to perform as requested. Creating
a GitHub release, opening a pull request, changing repository topics, or otherwise
mutating GitHub requires the user’s explicit intent. Theme and fixture HTML/JavaScript
are untrusted executable inputs; keep browser checks loopback-only and deny external
requests.
