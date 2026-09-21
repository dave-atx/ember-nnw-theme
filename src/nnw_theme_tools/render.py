from __future__ import annotations

import base64
import hashlib
import html
import re
import shutil
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .project import ThemeError, read_fixture
from .snapshot import ensure_snapshot

MACRO_RE = re.compile(r"\[\[([a-zA-Z0-9_-]+)\]\]")
SCRIPT_RE = re.compile(r"<script\b[^>]*>.*?</script>", re.DOTALL | re.IGNORECASE)
# A whole <img> or <source> tag; quoted attribute values may contain ">".
MEDIA_TAG_RE = re.compile(r"""<(img|source)\b((?:[^>"']|"[^"]*"|'[^']*')*)>""", re.IGNORECASE)
ATTRIBUTE_RE = re.compile(r"""([^\s"'=<>/]+)(?:\s*=\s*("[^"]*"|'[^']*'|[^\s"'=<>`]+))?""")
TEMPLATE_KEYS = (
    "title",
    "preferred_link",
    "external_link_label",
    "external_link_stripped",
    "external_link",
    "feed_link_title",
    "feed_link",
    "byline",
    "avatar_src",
    "dateline_style",
    "datetime_long",
    "datetime_medium",
    "datetime_short",
    "date_long",
    "date_medium",
    "date_short",
    "time_long",
    "time_medium",
    "time_short",
    "text_size_class",
    "body",
)
# macOS scales through text_size_class, iOS through the font-size macro. largeText
# is the macOS default: an unset preference falls back to ArticleTextSize.large.
DEFAULT_TEXT_SIZE_CLASS = "largeText"
LARGE_TEXT_SIZE_CLASS = "xxLargeText"
DEFAULT_DYNAMIC_TYPE_SIZE = 17.0
LARGE_DYNAMIC_TYPE_SIZE = 23.0
WEBKIT_SHIM = """
window.webkit = window.webkit || {messageHandlers: new Proxy({}, {
  get: function() { return {postMessage: function() {}}; }
})};
"""
# The iOS app injects the feed icon's localized accessibility label for main_ios.js
# (WebViewConfiguration.feedInfoLabelScript); templates with #nnwImageIcon need it.
IOS_LABEL_SHIM = """
const nnwGetFeedInfoLabel = "Get Feed Info";
"""
PLATFORM_NAMES = {"mac": "Mac", "iphone": "iPhone", "ipad": "iPad"}
VIEWPORTS = {"mac": (1280, 800), "iphone": (393, 852), "ipad": (834, 1112)}
# The template's own fixtures get the full matrix and the stress cases. Any other
# fixture a theme adds is an extra: checked on Mac and iPhone in both appearances.
FIXTURE_NAMES = {"article": "Article", "kitchen-sink": "Kitchen sink"}
EXTRA_PLATFORMS = ("mac", "iphone")
# Gallery sections, in order: (scenario, heading, what the scenario covers).
SCENARIOS = (
    (
        "article",
        "Everyday reading",
        "The article fixture: a typical short post with a headline, byline, standfirst, "
        "prose, and a pull quote.",
    ),
    (
        "kitchen-sink",
        "Stress test",
        "The kitchen-sink fixture: a very long headline, byline, and feed name; inline "
        "formatting; nested lists; an unbroken identifier that exposes horizontal "
        "overflow; a quotation, code block, table, figure, and footnote.",
    ),
    (
        "large-text",
        "Large text",
        "The kitchen-sink fixture at a large reading size: the xxLargeText size class on "
        "Mac and 23 pt Dynamic Type on iPhone.",
    ),
    (
        "article-javascript-off",
        "Article JavaScript off",
        "The article fixture with the theme's own scripts removed, as when a reader turns "
        "off NetNewsWire's Article JavaScript setting. It must still read well.",
    ),
)
CHECKS = (
    "article content renders",
    "no unresolved [[macros]]",
    "no horizontal overflow",
    "no broken images",
    "no external requests",
    "no JavaScript errors",
)


@dataclass(frozen=True)
class RenderTarget:
    fixture: str
    platform: str
    appearance: str
    width: int
    height: int
    large_text: bool = False
    theme_scripts: bool = True

    @property
    def ios(self) -> bool:
        return self.platform in {"iphone", "ipad"}

    @property
    def label(self) -> str:
        parts = [FIXTURE_NAMES.get(self.fixture, self.fixture), PLATFORM_NAMES[self.platform]]
        parts.append(self.appearance)
        if self.large_text:
            parts.append("large text")
        if not self.theme_scripts:
            parts.append("Article JavaScript off")
        return " · ".join(parts)

    @property
    def scenario(self) -> str:
        if self.large_text:
            return "large-text"
        if not self.theme_scripts:
            return "article-javascript-off"
        return self.fixture

    @property
    def slug(self) -> str:
        parts = [self.fixture, self.platform, self.appearance]
        if self.large_text:
            parts.append("large-text")
        if not self.theme_scripts:
            parts.append("no-article-js")
        return "-".join(parts)


def extra_fixtures(root: Path) -> list[str]:
    """Fixture names beyond the template's own, in gallery order."""
    names = sorted(path.stem for path in (root / "fixtures").glob("*.toml"))
    extras = [name for name in names if name not in FIXTURE_NAMES]
    reserved = sorted({scenario for scenario, _, _ in SCENARIOS} & set(extras))
    if reserved:
        raise ThemeError(
            f"fixture name(s) reserved for a check scenario: {', '.join(reserved)}; "
            "rename the file"
        )
    return extras


def normal_targets(extras: Sequence[str] = ()) -> list[RenderTarget]:
    return [
        RenderTarget(fixture, platform, appearance, *VIEWPORTS[platform])
        for fixture in FIXTURE_NAMES
        for platform in PLATFORM_NAMES
        for appearance in ("light", "dark")
    ] + [
        RenderTarget(fixture, platform, appearance, *VIEWPORTS[platform])
        for fixture in extras
        for platform in EXTRA_PLATFORMS
        for appearance in ("light", "dark")
    ]


def check_targets(extras: Sequence[str] = ()) -> list[RenderTarget]:
    return [
        *normal_targets(extras),
        RenderTarget("kitchen-sink", "mac", "light", 1280, 800, large_text=True),
        RenderTarget("kitchen-sink", "iphone", "light", 393, 852, large_text=True),
        RenderTarget("article", "mac", "light", 1280, 800, theme_scripts=False),
        RenderTarget("article", "iphone", "light", 393, 852, theme_scripts=False),
    ]


def substitute(template: str, mapping: dict[str, Any]) -> str:
    """Perform NetNewsWire's single-pass, non-recursive macro substitution."""

    return MACRO_RE.sub(
        lambda match: str(mapping.get(match.group(1), match.group(0))), template
    )


def _avatar_data_uri(title: str) -> str:
    words = title.strip().split()
    initials = "?" if not words else "".join(word[0] for word in words[:3]).upper()
    hue = int(hashlib.sha256(title.encode()).hexdigest()[:2], 16) / 255 * 360
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="96" height="96">'
        f'<rect width="96" height="96" rx="18" fill="hsl({hue:.0f} 42% 38%)"/>'
        '<text x="48" y="50" text-anchor="middle" dominant-baseline="central" '
        'font-family="system-ui" font-size="32" font-weight="700" fill="white">'
        f"{html.escape(initials)}</text></svg>"
    )
    encoded = base64.b64encode(svg.encode()).decode()
    return f"data:image/svg+xml;base64,{encoded}"


def _fetches(url: str) -> bool:
    """Whether a URL would load over the network, including relative to the base URL."""
    url = url.strip().lower()
    return bool(url) and not url.startswith(("data:", "#"))


def _placeholder(width: str | None, height: str | None) -> str:
    size = [int(value) if value and value.isdigit() else 0 for value in (width, height)]
    width_px, height_px = size if all(size) else (1600, 900)
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width_px}" height="{height_px}">'
        '<rect width="100%" height="100%" fill="#8a8f98" fill-opacity=".35"/></svg>'
    )
    return f"data:image/svg+xml;base64,{base64.b64encode(svg.encode()).decode()}"


def offline_media(body: str) -> str:
    """Swap a fixture's network images for same-size placeholders.

    Previews never touch the network, so a captured article's images would otherwise
    render broken. Each <img> keeps its attributes and width/height (16:9 when it has
    none), so layout matches; a <source> that would fetch is dropped for its <img>.
    """

    def replace(match: re.Match[str]) -> str:
        tag = match.group(1).lower()
        attributes = ATTRIBUTE_RE.findall(match.group(2))
        values = {name.lower(): html.unescape(value.strip("\"'")) for name, value in attributes}
        srcset = any(_fetches(part) for part in values.get("srcset", "").split(","))
        if not (srcset or _fetches(values.get("src", ""))):
            return match.group(0)
        if tag == "source":
            return ""
        kept = "".join(
            f" {name}={value}" if value else f" {name}"
            for name, value in attributes
            if name.lower() not in {"src", "srcset", "sizes"}
        )
        placeholder = _placeholder(values.get("width"), values.get("height"))
        return f'<{match.group(1)}{kept} src="{placeholder}">'

    return MEDIA_TAG_RE.sub(replace, body)


def _fixture_mapping(fixture: dict[str, Any], target: RenderTarget) -> dict[str, str]:
    mapping = {key: str(fixture.get(key, "")) for key in TEMPLATE_KEYS}
    if not mapping["dateline_style"]:
        mapping["dateline_style"] = (
            "articleDateline" if mapping["title"] else "articleDatelineTitle"
        )
    mapping["body"] = offline_media(mapping["body"])
    if not mapping["avatar_src"] or _fetches(mapping["avatar_src"]):
        mapping["avatar_src"] = _avatar_data_uri(mapping["feed_link_title"])
    if target.ios:
        # NetNewsWire leaves this macro unresolved on iOS; empty renders the same.
        mapping["text_size_class"] = ""
    else:
        default = LARGE_TEXT_SIZE_CLASS if target.large_text else DEFAULT_TEXT_SIZE_CLASS
        mapping["text_size_class"] = str(fixture.get("text_size_class") or default)
    return mapping


def _inject_scripts(page: str, rendering_inputs: Path, platform: str) -> str:
    platform_dir = "iOS" if platform in {"iphone", "ipad"} else "Mac"
    platform_script = "main_ios.js" if platform_dir == "iOS" else "main_mac.js"
    scripts = [WEBKIT_SHIM]
    if platform_dir == "iOS":
        scripts.append(IOS_LABEL_SHIM)
    for path in (
        rendering_inputs / "Shared" / "main.js",
        rendering_inputs / platform_dir / platform_script,
        rendering_inputs / "Shared" / "newsfoot.js",
    ):
        scripts.append(path.read_text(encoding="utf-8"))
    bundle = "\n".join(f"<script>\n{script}\n</script>" for script in scripts)
    return page.replace("</body>", f"{bundle}\n</body>", 1)


def render_page(
    root: Path,
    theme: Path,
    fixture: dict[str, Any],
    target: RenderTarget,
    *,
    snapshot: Path | None = None,
) -> str:
    rendering_inputs = snapshot or ensure_snapshot(root).path
    page_path = rendering_inputs / ("iOS" if target.ios else "Mac") / "page.html"
    required = [
        page_path,
        rendering_inputs / "Shared" / "core.css",
        rendering_inputs / "Shared" / "main.js",
    ]
    if not all(path.is_file() for path in required):
        raise ThemeError("cached NetNewsWire rendering inputs are incomplete")

    skeleton = SCRIPT_RE.sub("", page_path.read_text(encoding="utf-8"))
    stylesheet = (theme / "stylesheet.css").read_text(encoding="utf-8")
    # styleSubstitutions() is empty on macOS, so the macro must stay literal there.
    style_substitutions: dict[str, str] = {}
    if target.ios:
        size = LARGE_DYNAMIC_TYPE_SIZE if target.large_text else DEFAULT_DYNAMIC_TYPE_SIZE
        style_substitutions["font-size"] = f"{float(fixture.get('font_size', size)):g}"
    style = substitute(
        (rendering_inputs / "Shared" / "core.css").read_text(encoding="utf-8")
        + "\n"
        + stylesheet,
        style_substitutions,
    )

    template = (theme / "template.html").read_text(encoding="utf-8")
    body = substitute(template, _fixture_mapping(fixture, target))
    if not target.theme_scripts:
        body = SCRIPT_RE.sub("", body)
    page = substitute(
        skeleton,
        {
            "title": fixture.get("title", "Theme preview"),
            "style": style,
            "body": body,
            "baseURL": fixture.get("preferred_link") or fixture.get("feed_link") or "",
            "windowScrollY": "0",
        },
    )
    page = _inject_scripts(page, rendering_inputs, target.platform)
    csp = (
        "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; "
        "img-src data:; media-src data:; connect-src 'none'; frame-src 'none'; "
        "object-src 'none'; base-uri http: https:; form-action 'none'"
    )
    head = (
        '<meta charset="utf-8">\n'
        '<meta name="color-scheme" content="light dark">\n'
        f'<meta http-equiv="Content-Security-Policy" content="{csp}">'
    )
    return re.sub(r"(<head[^>]*>)", rf"\1\n{head}", page, count=1, flags=re.IGNORECASE)


def render_site(
    root: Path,
    theme: Path,
    targets: list[RenderTarget],
    *,
    snapshot: Path | None = None,
) -> Path:
    rendering_inputs = snapshot or ensure_snapshot(root).path
    site = root / "build" / "preview"
    if site.exists():
        shutil.rmtree(site)
    pages = site / "pages"
    views = site / "views"
    pages.mkdir(parents=True, exist_ok=True)
    views.mkdir(parents=True, exist_ok=True)
    (site / "screenshots").mkdir(parents=True, exist_ok=True)
    for target in targets:
        fixture = read_fixture(root / "fixtures" / f"{target.fixture}.toml")
        destination = pages / f"{target.slug}.html"
        destination.write_text(
            render_page(root, theme, fixture, target, snapshot=rendering_inputs),
            encoding="utf-8",
        )
        viewer = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>{html.escape(target.label)} · {html.escape(theme.stem)} preview</title><style>
html,body,iframe {{ border: 0; height: 100%; margin: 0; width: 100%; }}
</style></head><body><iframe src="../pages/{target.slug}.html" sandbox="allow-scripts"
style="color-scheme: {target.appearance}"
title="Sandboxed {html.escape(target.label)} theme preview"></iframe></body></html>"""
        (views / f"{target.slug}.html").write_text(viewer, encoding="utf-8")
    write_gallery(site, theme.stem, targets)
    return site


def _case(target: RenderTarget, failures: list[str] | None) -> str:
    slug = html.escape(target.slug)
    label = html.escape(target.label)
    shot = f"screenshots/{slug}.png"
    status = ""
    if failures is not None:
        status = (
            '<span class="badge fail">✗ Failed</span>'
            if failures
            else '<span class="badge pass">✓ Passed</span>'
        )
    reasons = "".join(f"<li>{html.escape(reason)}</li>" for reason in failures or [])
    # The live page renders at the real viewport size and is scaled into the thumbnail;
    # the checked screenshot covers it once it exists.
    return (
        f'<figure class="case{" failed" if failures else ""}" id="{slug}">'
        f'<a class="thumb" href="views/{slug}.html" '
        f'style="aspect-ratio: {target.width} / {target.height}">'
        f'<iframe loading="lazy" src="pages/{slug}.html" sandbox="allow-scripts" '
        f'tabindex="-1" width="{target.width}" height="{target.height}" '
        f'style="color-scheme: {target.appearance}" '
        f'title="Sandboxed {label} theme preview"></iframe>'
        f'<img src="{shot}" alt="Checked screenshot: {label}" '
        'onload="this.previousElementSibling.remove()" onerror="this.remove()"></a>'
        f"<figcaption>{status}"
        f'<a href="views/{slug}.html">Full size</a>'
        f"{f' · <a href={shot}>Screenshot</a>' if failures is not None else ''}"
        f"{f'<ul class=reasons>{reasons}</ul>' if reasons else ''}</figcaption></figure>"
    )


def _section(
    heading: str,
    description: str,
    targets: list[RenderTarget],
    results: dict[str, list[str]] | None,
) -> str:
    platforms = [name for name in PLATFORM_NAMES if any(t.platform == name for t in targets)]
    appearances = [
        name for name in ("light", "dark") if any(t.appearance == name for t in targets)
    ]
    header = "".join(f'<div class="column">{name.title()}</div>' for name in appearances)
    by_cell = {(t.platform, t.appearance): t for t in targets}
    rows = []
    for platform in platforms:
        cells = [
            _case(target, None if results is None else results.get(target.slug, []))
            if (target := by_cell.get((platform, appearance)))
            else "<div></div>"
            for appearance in appearances
        ]
        rows.append(f'<div class="row-label">{PLATFORM_NAMES[platform]}</div>{"".join(cells)}')
    return (
        f"<section><h2>{html.escape(heading)}</h2><p>{html.escape(description)}</p>"
        f'<div class="matrix" style="--columns: {len(appearances)}">'
        f"<div></div>{header}{''.join(rows)}</div></section>"
    )


def write_gallery(
    site: Path,
    theme_name: str,
    targets: list[RenderTarget],
    results: dict[str, list[str]] | None = None,
) -> None:
    """Write index.html; results maps each checked slug to its failures."""
    sections = []
    known = {scenario for scenario, _, _ in SCENARIOS}
    extra = [
        (target.scenario, target.fixture, f"Your fixtures/{target.fixture}.toml.")
        for target in targets
        if target.scenario not in known
    ]
    for scenario, heading, description in (*SCENARIOS, *dict.fromkeys(extra)):
        members = [target for target in targets if target.scenario == scenario]
        if members:
            sections.append(_section(heading, description, members, results))

    if results is None:
        summary = (
            f"<p class=summary>{len(targets)} cases, not checked yet. Run "
            "<code>uv run nnw-theme check</code> to verify them in WebKit.</p>"
        )
        failed_list = ""
    else:
        failed = [target for target in targets if results.get(target.slug)]
        summary = (
            f'<p class="summary {"fail" if failed else "pass"}">{len(targets)} cases · '
            f"{len(targets) - len(failed)} passed · {len(failed)} failed</p>"
        )
        failed_list = (
            "<section class=failures><h2>Failures</h2><ul>"
            + "".join(
                f'<li><a href="#{html.escape(t.slug)}">{html.escape(t.label)}</a>: '
                f"{html.escape('; '.join(results[t.slug]))}</li>"
                for t in failed
            )
            + "</ul></section>"
            if failed
            else ""
        )
    checks = "".join(f"<li>{html.escape(check)}</li>" for check in CHECKS)
    gallery = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg'/%3E">
<title>{html.escape(theme_name)} preview</title><style>
:root {{ color-scheme: light dark; font-family: system-ui; --pass: #1a7f37; --fail: #cf222e;
  --line: color-mix(in srgb, CanvasText 18%, Canvas);
  --wash: color-mix(in srgb, CanvasText 6%, Canvas); }}
@media (prefers-color-scheme: dark) {{ :root {{ --pass: #3fb950; --fail: #f85149; }} }}
body {{ background: Canvas; color: CanvasText; line-height: 1.45; margin: 0 auto;
  max-width: 72rem; padding: 1.5rem 1rem 4rem; }}
.notice {{ background: var(--wash); border-radius: .4rem; font-size: .9rem;
  margin: 0 0 1.5rem; padding: .6rem .9rem; }}
h1 {{ margin: 0 0 .3rem; }} h2 {{ margin: 0 0 .25rem; }}
.summary {{ font-size: 1.1rem; font-weight: 600; margin: 0 0 .5rem; }}
.summary.pass {{ color: var(--pass); }} .summary.fail {{ color: var(--fail); }}
details {{ margin-bottom: 1rem; }} summary {{ cursor: pointer; }}
section {{ border-top: 1px solid var(--line); padding: 1.5rem 0 .5rem; }}
section > p {{ margin: 0 0 1rem; max-width: 46rem; }}
.failures li {{ margin-bottom: .3rem; }} .failures a {{ color: var(--fail); }}
.matrix {{ align-items: start; display: grid; gap: 1rem 1.25rem;
  grid-template-columns: 4rem repeat(var(--columns), minmax(0, 1fr)); }}
.column {{ font-weight: 600; }}
.row-label {{ font-weight: 600; padding-top: .3rem; }}
.case {{ margin: 0; }}
.thumb {{ background: var(--wash); border: 1px solid var(--line); border-radius: .5rem;
  display: block; height: 20rem; max-width: 100%; overflow: hidden; position: relative;
  width: auto; }}
.case.failed .thumb {{ border: 2px solid var(--fail); }}
.thumb iframe {{ border: 0; left: 0; pointer-events: none; position: absolute; top: 0;
  transform-origin: 0 0; }}
.thumb img {{ display: block; height: 100%; object-fit: cover; object-position: top;
  width: 100%; }}
figcaption {{ font-size: .85rem; margin-top: .4rem; }}
.badge {{ font-weight: 600; margin-right: .5rem; }}
.badge.pass {{ color: var(--pass); }} .badge.fail {{ color: var(--fail); }}
.reasons {{ color: var(--fail); margin: .3rem 0 0; padding-left: 1.1rem; }}
@media (max-width: 40rem) {{
  .matrix {{ grid-template-columns: repeat(var(--columns), minmax(0, 1fr)); }}
  .matrix > div:first-child {{ display: none; }}
  .row-label {{ grid-column: 1 / -1; padding: 0; }}
  .thumb {{ height: auto; width: 100%; }}
}}
</style></head><body>
<p class="notice">Development preview. Install themes only from a release.</p>
<h1>{html.escape(theme_name)} preview</h1>
{summary}
<details><summary>What every case checks</summary><ul>{checks}</ul></details>
{failed_list}{"".join(sections)}
<script>
// Scale each live page from its real viewport width down to the thumbnail.
const fit = frame => {{ frame.style.transform =
  `scale(${{frame.parentElement.clientWidth / frame.width}})`; }};
const observer = new ResizeObserver(entries =>
  entries.forEach(entry => entry.target.querySelectorAll("iframe").forEach(fit)));
document.querySelectorAll(".thumb").forEach(thumb => observer.observe(thumb));
</script></body></html>"""
    (site / "index.html").write_text(gallery, encoding="utf-8")
