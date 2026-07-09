#!/usr/bin/env python3
"""Render an .nnwtheme against a fixture, reproducing NetNewsWire's assembly.

NetNewsWire builds the HTML document it loads into its WKWebView by taking a
platform "page skeleton" (page.html) and filling three macros in it:
[[title]], [[style]], [[body]] (plus [[baseURL]] and [[windowScrollY]] on
iOS). The style block is core.css + the theme's stylesheet.css, with
[[font-size]] substituted. The body block is the theme's template.html, with
the article's fixture data substituted. This script reproduces that pipeline
exactly (single-pass, non-recursive macro substitution) so a theme developer
can preview or screenshot a theme against a captured article fixture without
running NetNewsWire itself.

Usage:
    python3 render.py FIXTURE.toml [--platform {mac,ios,ipad,all}]
        [--theme DIR] [--nnw DIR] [--out DIR] [--keep-scripts] [--open]
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import re
import subprocess
import sys
import tomllib
from pathlib import Path

MACRO_RE = re.compile(r"\[\[([a-zA-Z0-9_-]+)\]\]")

TEMPLATE_KEYS = [
    "title", "preferred_link", "external_link_label", "external_link_stripped",
    "external_link", "feed_link_title", "feed_link", "byline", "avatar_src",
    "dateline_style", "datetime_long", "datetime_medium", "datetime_short",
    "date_long", "date_medium", "date_short", "time_long", "time_medium",
    "time_short", "text_size_class", "body",
]

SCRIPT_RE = re.compile(r"<script\b[^>]*>.*?</script>", re.DOTALL | re.IGNORECASE)

PCS_DARK_RE = re.compile(r"\(\s*prefers-color-scheme\s*:\s*dark\s*\)", re.IGNORECASE)
PCS_LIGHT_RE = re.compile(r"\(\s*prefers-color-scheme\s*:\s*light\s*\)", re.IGNORECASE)


def force_dark(css: str) -> str:
    """Make `prefers-color-scheme` dark rules win in any engine.

    The Safari MCP (and file:// previews generally) can't emulate a color
    scheme, so to preview dark mode we rewrite the media *feature* — leaving any
    combined conditions (e.g. `screen and (...)`) and nesting intact — so dark
    blocks always match and light blocks never do.
    """
    css = PCS_DARK_RE.sub("(min-width: 0px)", css)
    css = PCS_LIGHT_RE.sub("(max-width: 0px)", css)
    return css


def substitute(template: str, mapping: dict) -> str:
    """Single-pass, non-recursive [[key]] substitution.

    Known keys are replaced with their mapping value (used verbatim, never
    re-scanned for further macros). Unknown keys are left literally in place.
    """
    def repl(m: re.Match) -> str:
        key = m.group(1)
        if key in mapping:
            return str(mapping[key])
        return m.group(0)
    return MACRO_RE.sub(repl, template)


def find_theme(fixture_path: Path) -> Path:
    for d in [fixture_path.parent, *fixture_path.parent.parents]:
        themes = list(d.glob("*.nnwtheme"))
        if len(themes) == 1:
            return themes[0]
        if len(themes) > 1:
            sys.exit(
                f"error: multiple .nnwtheme bundles found in {d}: "
                f"{[t.name for t in themes]}; pass --theme"
            )
    sys.exit(
        "error: could not find a *.nnwtheme directory by walking up from "
        f"{fixture_path}; pass --theme"
    )


def find_repo_root(theme_dir: Path) -> Path:
    return theme_dir.parent


def avatar_color(feed_link_title: str) -> str:
    digest = hashlib.sha256(feed_link_title.encode("utf-8")).digest()
    hue = digest[0] / 255.0 * 360.0
    # Medium-dark, saturated so white text is legible.
    return hsl_to_hex(hue, 0.55, 0.40)


def hsl_to_hex(h: float, s: float, l: float) -> str:
    c = (1 - abs(2 * l - 1)) * s
    x = c * (1 - abs((h / 60.0) % 2 - 1))
    m = l - c / 2
    if h < 60:
        r, g, b = c, x, 0.0
    elif h < 120:
        r, g, b = x, c, 0.0
    elif h < 180:
        r, g, b = 0.0, c, x
    elif h < 240:
        r, g, b = 0.0, x, c
    elif h < 300:
        r, g, b = x, 0.0, c
    else:
        r, g, b = c, 0.0, x
    r, g, b = (round((v + m) * 255) for v in (r, g, b))
    return f"#{r:02x}{g:02x}{b:02x}"


def avatar_initials(feed_link_title: str) -> str:
    title = feed_link_title.strip()
    if not title:
        return "?"
    words = title.split()
    if len(words) == 1:
        return words[0][:3].upper()
    return "".join(w[0] for w in words[:3]).upper()


def make_avatar_data_uri(feed_link_title: str) -> str:
    color = avatar_color(feed_link_title or "")
    initials = avatar_initials(feed_link_title or "")
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="96" height="96" '
        'viewBox="0 0 96 96">'
        f'<rect width="96" height="96" rx="18" fill="{color}"/>'
        '<text x="48" y="48" text-anchor="middle" dominant-baseline="central" '
        'font-family="-apple-system, Helvetica, Arial, sans-serif" '
        'font-size="34" font-weight="700" fill="#ffffff">'
        f'{html_escape(initials)}</text></svg>'
    )
    b64 = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{b64}"


def html_escape(s: str) -> str:
    import html
    return html.escape(s, quote=True)


def build_fixture_dict(fixture: dict) -> dict:
    data = {key: str(fixture.get(key, "")) for key in TEMPLATE_KEYS}
    if "dateline_style" not in fixture:
        data["dateline_style"] = "articleDatelineTitle" if not data["title"] else "articleDateline"
    avatar_src = data.get("avatar_src", "")
    if avatar_src.startswith("nnwImageIcon:") or avatar_src == "":
        data["avatar_src"] = make_avatar_data_uri(data.get("feed_link_title", ""))
    return data


def render_platform(platform: str, fixture: dict, theme_dir: Path, nnw_dir: Path, keep_scripts: bool, dark: bool = False) -> str:
    is_ios = platform in ("ios", "ipad")
    skeleton_path = (
        nnw_dir / "Mac" / "MainWindow" / "Detail" / "page.html"
        if platform == "mac"
        else nnw_dir / "iOS" / "Resources" / "page.html"
    )
    core_css = (nnw_dir / "Shared" / "Article Rendering" / "core.css").read_text()
    stylesheet_css = (theme_dir / "stylesheet.css").read_text()
    template_html = (theme_dir / "template.html").read_text()
    skeleton_html = skeleton_path.read_text()

    style_mapping = {}
    if is_ios:
        font_size = fixture.get("font_size", 17)
        style_mapping["font-size"] = str(font_size)
    style_text = substitute(core_css + "\n" + stylesheet_css, style_mapping)
    if dark:
        style_text = force_dark(style_text)

    body_data = build_fixture_dict(fixture)
    body_data["text_size_class"] = "" if is_ios else (fixture.get("text_size_class") or "mediumText")
    body_html = substitute(template_html, body_data)

    page_mapping = {
        "title": fixture.get("title") or "Preview",
        "style": style_text,
        "body": body_html,
        "baseURL": fixture.get("preferred_link") or fixture.get("feed_link") or "",
        "windowScrollY": "0",
    }
    page = substitute(skeleton_html, page_mapping)

    if not keep_scripts:
        page = SCRIPT_RE.sub("", page)

    # NNW loads the document via loadHTMLString, which defaults to UTF-8. A
    # file:// preview has no such hint, so WebKit would guess (and mangle smart
    # quotes / em dashes). Declare the charset to match in-app rendering.
    head_inject = '\n\t\t<meta charset="utf-8">'
    if dark:
        # Make the UA (scrollbars, form controls, default canvas) dark too.
        head_inject += '\n\t\t<meta name="color-scheme" content="dark">'
    if "charset" not in page.lower():
        page = re.sub(r"(<head[^>]*>)", lambda m: m.group(1) + head_inject,
                      page, count=1, flags=re.IGNORECASE)

    return page


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Render an NNW theme against an article fixture, reproducing "
        "NetNewsWire's own HTML assembly, for preview/screenshotting."
    )
    parser.add_argument("fixture", type=Path, help="Path to a fixture TOML file")
    parser.add_argument(
        "--platform", choices=["mac", "ios", "ipad", "all"], default="all",
        help="Which platform skeleton to render (default: all -> mac + ios)",
    )
    parser.add_argument("--theme", type=Path, default=None, help="Theme .nnwtheme directory (default: auto-detect)")
    parser.add_argument("--nnw", type=Path, default=None, help="NetNewsWire source checkout (default: $NNW_SRC or <repo_root>/../NetNewsWire)")
    parser.add_argument("--out", type=Path, default=None, help="Output directory (default: <repo_root>/test/preview/)")
    parser.add_argument("--dark", action="store_true", help="Force the theme's dark (prefers-color-scheme: dark) rules; writes .dark.html files")
    parser.add_argument("--keep-scripts", action="store_true", help="Do not strip <script> tags from the rendered HTML")
    parser.add_argument("--open", action="store_true", help="Open each rendered file with the macOS `open` command")
    args = parser.parse_args()

    fixture_path = args.fixture.resolve()
    if not fixture_path.is_file():
        sys.exit(f"error: fixture not found: {fixture_path}")

    theme_dir = args.theme.resolve() if args.theme else find_theme(fixture_path)
    if not theme_dir.is_dir():
        sys.exit(f"error: theme directory not found: {theme_dir}")
    for required in ("template.html", "stylesheet.css"):
        if not (theme_dir / required).is_file():
            sys.exit(f"error: theme is missing {required}: {theme_dir / required}")

    repo_root = find_repo_root(theme_dir)

    import os
    if args.nnw:
        nnw_dir = args.nnw.resolve()
    elif os.environ.get("NNW_SRC"):
        nnw_dir = Path(os.environ["NNW_SRC"]).resolve()
    else:
        nnw_dir = (repo_root / ".." / "NetNewsWire").resolve()

    required_nnw_files = [
        nnw_dir / "Shared" / "Article Rendering" / "core.css",
        nnw_dir / "Mac" / "MainWindow" / "Detail" / "page.html",
        nnw_dir / "iOS" / "Resources" / "page.html",
    ]
    if not all(p.is_file() for p in required_nnw_files):
        sys.exit(
            f"error: NetNewsWire source not found at {nnw_dir}; "
            "clone Ranchero-Software/NetNewsWire or pass --nnw / set NNW_SRC."
        )

    out_dir = args.out.resolve() if args.out else (repo_root / "test" / "preview")
    out_dir.mkdir(parents=True, exist_ok=True)

    with fixture_path.open("rb") as f:
        fixture = tomllib.load(f)

    if args.platform == "all":
        platforms = ["mac", "ios"]
    else:
        platforms = [args.platform]

    written = []
    suffix = ".dark" if args.dark else ""
    for platform in platforms:
        page = render_platform(platform, fixture, theme_dir, nnw_dir, args.keep_scripts, args.dark)
        out_path = out_dir / f"{fixture_path.stem}.{platform}{suffix}.html"
        out_path.write_text(page)
        written.append(out_path)
        print(out_path)

    print()
    print("Suggested screenshot viewports:")
    print("  iPhone 393x852  (uses the .ios.html file)")
    print("  iPad   834x1112 (uses the .ios.html file)")
    print("  macOS  1000x1200 (uses the .mac.html file)")

    if args.open:
        for path in written:
            subprocess.run(["open", str(path)], check=False)


if __name__ == "__main__":
    main()
