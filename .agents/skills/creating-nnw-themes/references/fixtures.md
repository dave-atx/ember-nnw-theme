# Fixtures

Read this when adding, capturing, or changing the articles previews render.

Each `fixtures/*.toml` is one article: keys are the template macros, and any omitted
key renders empty. `article` and `kitchen-sink` belong to the template and get the full
matrix plus the large-text and Article-JavaScript-off cases. Every other fixture is
checked on macOS and iPhone in light and dark. Names used by check scenarios
(`large-text`, `article-javascript-off`) are reserved. Use `'''literal'''` strings for
HTML bodies so they need no escaping.

Prefer real articles for content a theme must handle. `uv run nnw-theme capture`
prints the steps for saving the selected article from a NetNewsWire debug build with
the `nnwdump` lldb command; it needs Xcode and a NetNewsWire clone, so the person
usually runs it. Rendering swaps every image that would load over the network for a
same-size placeholder and a network feed icon for a generated one; do not inline or
fetch the originals.

Footnote markers are the links NetNewsWire's `newsfoot.js` handles: `a.footnote`.
Its `main.js` adds that class to local `sup > a[href*='#fn']` links; a theme script
may add it to other formats. `check` requires every visible marker to resolve to a
non-empty note with a unique id, stay legible on its background, match the other
markers' height, font size, and baseline offset, and open a popover with its note
without resizing. A fixture may declare exact expectations after its other keys:

```toml
[expect.footnotes]
plain_links = ["#ordinary-sup-link"]   # CSS selectors that must not become markers
keep_with_word = true                  # markers must not wrap apart from their word

[expect.footnotes.notes]
"1" = "First note."                    # marker text as rendered = note text
```

With `notes`, every listed marker must exist and any other marker fails. With
`keep_with_word`, a marker written against its word, with no space, must not wrap
onto a new line apart from it. NetNewsWire's `core.css` makes `a.footnote`
`inline-block`, which allows that break, and CSS alone cannot remove it: a theme
script must hold the pair together, for example in a `white-space: nowrap` span.
Expectations describe the theme's own scripts, so they are skipped with Article
JavaScript off.
