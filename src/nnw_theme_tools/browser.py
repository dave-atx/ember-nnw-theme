from __future__ import annotations

import contextlib
import json
import shutil
import subprocess
import sys
import threading
import uuid
from collections.abc import Mapping
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import quote

from .project import ThemeError
from .render import RenderTarget

FOOTNOTE_CHECK = (Path(__file__).parent / "footnotes.js").read_text(encoding="utf-8")


def _run(arguments: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(arguments, check=check, capture_output=True, text=True)
    except FileNotFoundError as error:
        raise ThemeError(
            "playwright-cli is not installed; install it first (on macOS run "
            "`brew install playwright-cli`), then run `uv run nnw-theme setup` "
            "to add the WebKit browser"
        ) from error
    except subprocess.CalledProcessError as error:
        detail = (error.stderr or error.stdout).strip()
        raise ThemeError(f"playwright-cli failed: {detail}") from error


def browser_inventory() -> str:
    if not shutil.which("playwright-cli"):
        return ""
    # Listing fails on a browser cache that has never had an install (it reads the
    # missing .links directory), so treat any failure as "nothing installed yet".
    result = _run(["playwright-cli", "install-browser", "--list"], check=False)
    return result.stdout if result.returncode == 0 else ""


def _webkit_runs() -> bool:
    session = f"nnw-setup-{uuid.uuid4().hex[:10]}"
    result = _run(
        ["playwright-cli", f"-s={session}", "open", "--browser=webkit", "about:blank"],
        check=False,
    )
    _run(["playwright-cli", f"-s={session}", "close"], check=False)
    return result.returncode == 0


def setup_webkit() -> None:
    if not shutil.which("playwright-cli"):
        raise ThemeError(
            "install playwright-cli first; on macOS run `brew install playwright-cli`, "
            "then run `uv run nnw-theme setup`"
        )
    inventory = browser_inventory()
    if "webkit" in inventory.lower() and _webkit_runs():
        print("WebKit is already installed.")
        return
    arguments = ["playwright-cli", "install-browser", "webkit"]
    if sys.platform.startswith("linux"):
        print("Installing WebKit and its Linux runtime dependencies…")
        arguments.append("--with-deps")
    else:
        print("Installing the WebKit browser used by theme checks…")
    _run(arguments)


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        return


@contextlib.contextmanager
def serve(directory: Path):
    handler = lambda *args, **kwargs: _QuietHandler(  # noqa: E731
        *args, directory=str(directory), **kwargs
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def _javascript(
    url: str, target: RenderTarget, screenshot: Path, footnotes: Mapping[str, Any]
) -> str:
    origin = "/".join(url.split("/", 3)[:3]).lower()
    return f"""async page => {{
  const blocked = [];
  const pageErrors = [];
  page.on('pageerror', error => pageErrors.push(String(error)));
  await page.context().route('**/*', async route => {{
    const requestURL = route.request().url();
    if (requestURL.startsWith('data:')) return route.continue();
    // Whole-origin match: a prefix test would accept 127.0.0.1:PORT.example.net.
    // No URL constructor in this sandbox, so match the authority explicitly.
    const match = /^([a-z][a-z0-9+.-]*:)\\/\\/([^/?#]*)/i.exec(requestURL);
    const requestOrigin = match ? (match[1] + '//' + match[2]).toLowerCase() : null;
    if (requestOrigin === {json.dumps(origin)}) return route.continue();
    blocked.push(requestURL);
    return route.abort('blockedbyclient');
  }});
  await page.setViewportSize({{width: {target.width}, height: {target.height}}});
  await page.emulateMedia({{colorScheme: {json.dumps(target.appearance)}}});
  await page.goto({json.dumps(url)}, {{waitUntil: 'networkidle'}});
  await page.screenshot({{path: {json.dumps(str(screenshot))}, fullPage: true}});
  const state = await page.evaluate(() => {{
    const root = document.documentElement;
    return {{
      article: Boolean(document.querySelector('.articleBody')),
      textLength: (document.querySelector('.articleBody')?.innerText || '').trim().length,
      // Body only: macOS CSS legitimately keeps the font-size macro literal. Match
      // whole macro names, so a theme script's regex such as /[[(]/ is no macro.
      unresolved: /\\[\\[[A-Za-z0-9_-]+\\]\\]/.test(document.body.innerHTML),
      overflow: root.scrollWidth > root.clientWidth + 1,
      brokenImages: [...document.images]
        .filter(image => image.complete && image.naturalWidth === 0)
        .map(image => image.currentSrc || image.src),
      title: document.title
    }};
  }});
  // Last: it clicks footnotes open, so it must not disturb the screenshot.
  const footnotes = await page.evaluate({FOOTNOTE_CHECK}, {json.dumps(dict(footnotes))});
  return JSON.stringify({{...state, footnotes, blocked, pageErrors}});
}}"""


def _parse_state(output: str) -> dict[str, object]:
    try:
        value = json.loads(output.strip())
        if isinstance(value, str):
            value = json.loads(value)
    except json.JSONDecodeError as error:
        raise ThemeError(f"could not read playwright-cli result: {output.strip()}") from error
    if not isinstance(value, dict):
        raise ThemeError(f"playwright-cli returned an unexpected result: {value!r}")
    return value


def _failures(state: dict[str, Any]) -> list[str]:
    failures = []
    if not state["article"] or state["textLength"] < 40:
        failures.append("article content is missing or unreadable")
    if state["unresolved"]:
        failures.append("unresolved theme macro")
    if state["overflow"]:
        failures.append("horizontal document overflow")
    if state["brokenImages"]:
        failures.append(f"broken images: {state['brokenImages']}")
    failures.extend(state.get("footnotes") or [])
    if state["blocked"]:
        failures.append(f"external requests: {state['blocked']}")
    if state["pageErrors"]:
        failures.append(f"page errors: {state['pageErrors']}")
    return failures


class CheckProgress(Protocol):
    def status(self, message: str) -> None: ...
    def start(self, index: int, target: RenderTarget) -> None: ...
    def finish(self, index: int, target: RenderTarget, failures: list[str]) -> None: ...


def check_pages(
    site: Path,
    targets: list[RenderTarget],
    progress: CheckProgress | None = None,
    expectations: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, list[str]]:
    """Each target's slug mapped to its failures (empty when it passed).

    expectations maps a fixture name to its [expect.footnotes] table. They describe
    the theme's own footnote handling, so they are skipped with theme scripts off.
    """
    results: dict[str, list[str]] = {}
    screenshots = site / "screenshots"
    screenshots.mkdir(parents=True, exist_ok=True)
    session = f"nnw-{uuid.uuid4().hex[:10]}"
    with serve(site) as base_url:
        if progress:
            progress.status("Starting WebKit…")
        _run(["playwright-cli", f"-s={session}", "open", "--browser=webkit", "about:blank"])
        try:
            for index, target in enumerate(targets, 1):
                if progress:
                    progress.start(index, target)
                url = f"{base_url}/pages/{quote(target.slug)}.html"
                screenshot = screenshots / f"{target.slug}.png"
                footnotes = (expectations or {}).get(target.fixture, {})
                if not target.theme_scripts:
                    footnotes = {}
                result = _run(
                    [
                        "playwright-cli",
                        "--raw",
                        f"-s={session}",
                        "run-code",
                        _javascript(url, target, screenshot, footnotes),
                    ]
                )
                target_failures = _failures(_parse_state(result.stdout))
                results[target.slug] = target_failures
                if progress:
                    progress.finish(index, target, target_failures)
        finally:
            _run(["playwright-cli", f"-s={session}", "close"], check=False)
    return results
