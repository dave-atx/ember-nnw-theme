from __future__ import annotations

import argparse
import json
import plistlib
import re
import shutil
import subprocess
import sys
import time
import webbrowser
import zipfile
from pathlib import Path
from typing import Any, TextIO
from urllib.parse import urlparse

from .browser import check_pages, serve, setup_webkit
from .package import build_archive
from .project import (
    IDENTITY_END,
    IDENTITY_START,
    PLACEHOLDER_MARKER,
    ThemeError,
    find_root,
    find_theme,
    footnote_expectations,
    read_fixture,
    read_plist,
    write_plist,
)
from .render import (
    RenderTarget,
    check_targets,
    extra_fixtures,
    normal_targets,
    render_site,
    write_gallery,
)
from .snapshot import ensure_snapshot
from .update import update


def _slug(value: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", value.lower())).strip("-")


def _identifier_slug(value: str) -> str:
    return re.sub(r"[^a-z0-9-]+", "", _slug(value)) or "theme"


def _repository() -> dict[str, Any]:
    """Owner and fork status of the current repository, when gh can report them."""
    if not shutil.which("gh"):
        return {}
    result = subprocess.run(
        ["gh", "repo", "view", "--json", "owner,isFork"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        return {}
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _default_identifier(name: str, homepage: str, github_user: str | None) -> str:
    suffix = _identifier_slug(name)
    if github_user:
        return f"io.github.{_identifier_slug(github_user)}.{suffix}"
    hostname = (urlparse(homepage).hostname or "example.com").lower().split(".")
    domain = ".".join(reversed([_identifier_slug(part) for part in hostname]))
    return f"{domain}.{suffix}"


def _prompt_text(label: str, default: str) -> str:
    import questionary

    answer = questionary.text(label, default=default).ask()
    if answer is None:
        raise ThemeError("cancelled")
    return answer.strip()


def _prompt_confirm(label: str, default: bool = True) -> bool:
    import questionary

    answer = questionary.confirm(label, default=default).ask()
    if answer is None:
        raise ThemeError("cancelled")
    return answer


def _absolute_homepage(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ThemeError("creator home page must be an absolute HTTP(S) URL")
    if parsed.hostname in {"example.com", "www.example.com"}:
        raise ThemeError("creator home page must not use the example.com placeholder")
    return value


def _update_readme(root: Path, *, name: str, creator: str, homepage: str) -> None:
    readme = root / "README.md"
    text = readme.read_text(encoding="utf-8")
    start = text.find(IDENTITY_START)
    end = text.find(IDENTITY_END)
    if start < 0 or end < start:
        raise ThemeError("README identity markers are missing")
    replacement = (
        f"{IDENTITY_START}\n"
        f"# {name}\n\n"
        f"A NetNewsWire theme by [{creator}]({homepage}).\n"
        f"{IDENTITY_END}"
    )
    text = text[:start] + replacement + text[end + len(IDENTITY_END) :]
    readme.write_text(text, encoding="utf-8")


def marketplace_enable() -> bool:
    if not shutil.which("gh"):
        print(
            "Warning: GitHub CLI is not installed. Run `uv run nnw-theme marketplace enable` "
            "after installing and authenticating gh.",
            file=sys.stderr,
        )
        return False
    result = subprocess.run(
        ["gh", "repo", "edit", "--add-topic", "netnewswire-theme"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        print(
            "Warning: could not add the marketplace topic. "
            "Run `uv run nnw-theme marketplace enable` later.\n"
            + (result.stderr or result.stdout).strip(),
            file=sys.stderr,
        )
        return False
    print("Added the netnewswire-theme GitHub topic.")
    return True


def command_init(args: argparse.Namespace) -> None:
    root = find_root()
    theme = find_theme(root)
    if not (root / PLACEHOLDER_MARKER).exists():
        raise ThemeError(
            "this repository is already initialized; run `uv run nnw-theme setup` "
            "to install preview tools"
        )

    interactive = not all((args.name, args.creator, args.homepage))
    repository = _repository()
    if repository.get("isFork"):
        print(
            "Warning: this repository is a fork. The theme marketplace skips forks, so "
            "the theme will never be discovered. Start from GitHub's \"Use this "
            'template" button instead, then rerun initialization.',
            file=sys.stderr,
        )
    github_user = args.github_user or repository.get("owner", {}).get("login")
    name = args.name or _prompt_text("Theme name", "Quiet Reader")
    creator = args.creator or _prompt_text("Your name", "Theme Author")
    homepage_default = f"https://github.com/{github_user}" if github_user else ""
    homepage = _absolute_homepage(
        args.homepage
        or _prompt_text(
            "Your HTTP(S) home page (for example, your GitHub profile)", homepage_default
        )
    )
    proposed = args.identifier or _default_identifier(name, homepage, github_user)
    identifier = proposed
    if interactive and not args.identifier:
        identifier = _prompt_text("Stable theme identifier", proposed)
    if args.confirm_identifier:
        if args.confirm_identifier != identifier:
            raise ThemeError("--confirm-identifier must exactly match the chosen identifier")
    elif not _prompt_confirm(
        f"Use {identifier!r} permanently? It cannot change after the first release.",
        default=True,
    ):
        raise ThemeError("choose a permanent identifier and rerun initialization")

    if (
        not name.strip()
        or name in {".", ".."}
        or any(character in name for character in "/\\\0")
    ):
        raise ThemeError("theme name must be non-empty and cannot contain path separators")
    destination = root / f"{name}.nnwtheme"
    if destination.exists() and destination != theme:
        raise ThemeError(f"theme bundle already exists: {destination}")
    metadata = read_plist(theme)
    metadata.update(
        {
            "ThemeIdentifier": identifier,
            "Name": name,
            "CreatorHomePage": homepage,
            "CreatorName": creator,
            "Version": 1,
        }
    )
    if destination != theme:
        theme.rename(destination)
        theme = destination
    write_plist(theme / "Info.plist", metadata)
    _update_readme(root, name=name, creator=creator, homepage=homepage)
    (root / "screenshots" / "theme-preview.png").unlink(missing_ok=True)
    (root / PLACEHOLDER_MARKER).unlink()
    print(f"Initialized {theme.name} with identifier {identifier}.")
    print("Create a deliberate marketplace image with `uv run nnw-theme screenshot --promote`.")

    marketplace = args.marketplace
    if marketplace is None:
        marketplace = (
            "yes" if _prompt_confirm("Add this repository to the theme marketplace?") else "no"
        )
    if marketplace == "yes":
        marketplace_enable()

    install = args.install_browser
    if install is None and interactive:
        install = _prompt_confirm("Set up WebKit for previews now?")
    if install:
        # Initialization is already complete; a preview setup failure must not look like
        # an init failure, because rerunning init is refused from here on.
        try:
            snapshot = ensure_snapshot(root)
            print(f"NetNewsWire {snapshot.release} rendering inputs are ready.")
            setup_webkit()
        except ThemeError as error:
            print(
                f"Warning: initialization succeeded, but preview setup did not: {error}\n"
                "Finish preview setup later with `uv run nnw-theme setup`.",
                file=sys.stderr,
            )
    print("Next: describe the design you want, then run `uv run nnw-theme preview`.")


def _print_warnings(warnings: list[str]) -> None:
    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)


def command_package(args: argparse.Namespace) -> None:
    root = find_root()
    theme = find_theme(root)
    destination, warnings = build_archive(
        theme, root / args.output_dir, allow_remote_media=args.allow_remote_media
    )
    _print_warnings(warnings)
    print(destination)


def command_setup(_args: argparse.Namespace) -> None:
    root = find_root()
    snapshot = ensure_snapshot(root)
    if snapshot.downloaded:
        print(
            f"Downloaded and verified {len(snapshot.downloaded)} NetNewsWire "
            f"{snapshot.release} rendering inputs."
        )
    else:
        print(f"NetNewsWire {snapshot.release} rendering inputs are already verified.")
    setup_webkit()


def command_render(args: argparse.Namespace) -> None:
    root = find_root()
    theme = find_theme(root)
    targets = normal_targets(extra_fixtures(root))
    if args.fixtures:
        requested = set(args.fixtures)
        targets = [target for target in targets if target.fixture in requested]
        unknown = requested - {target.fixture for target in targets}
        if unknown:
            raise ThemeError(f"unknown fixture(s): {', '.join(sorted(unknown))}")
    site = render_site(root, theme, targets)
    print(site / "index.html")


def _expectations(root: Path, targets: list[RenderTarget]) -> dict[str, dict[str, Any]]:
    return {
        name: footnote_expectations(
            read_fixture(root / "fixtures" / f"{name}.toml"), f"fixtures/{name}.toml"
        )
        for name in dict.fromkeys(target.fixture for target in targets)
    }


class _CheckProgress:
    """One line rewritten in place on a terminal; one plain line per case elsewhere."""

    def __init__(self, total: int, stream: TextIO = sys.stderr) -> None:
        self.total = total
        self.stream = stream
        self.live = stream.isatty()

    def _write(self, text: str) -> None:
        self.stream.write(text)
        self.stream.flush()

    def status(self, message: str) -> None:
        self._write(f"\r\033[K{message}" if self.live else f"{message}\n")

    def start(self, index: int, target: RenderTarget) -> None:
        if self.live:
            self._write(f"\r\033[KChecking {index}/{self.total} · {target.label}")

    def finish(self, index: int, target: RenderTarget, failures: list[str]) -> None:
        if self.live and failures:
            self._write(f"\r\033[K✗ {target.label}: {'; '.join(failures)}\n")
        elif not self.live:
            outcome = f"FAILED: {'; '.join(failures)}" if failures else "passed"
            self._write(f"[{index}/{self.total}] {target.label} … {outcome}\n")

    def done(self) -> None:
        if self.live:
            self._write("\r\033[K")


def _offer_to_open(index: Path, choice: bool | None) -> None:
    interactive = sys.stdin.isatty() and sys.stdout.isatty()
    if choice is None:
        choice = interactive and _prompt_confirm("Open the preview?", default=True)
    if choice:
        webbrowser.open(index.as_uri())


def command_check(args: argparse.Namespace) -> None:
    root = find_root()
    theme = find_theme(root)
    targets = check_targets(extra_fixtures(root))
    expectations = _expectations(root, targets)
    progress = _CheckProgress(len(targets))
    progress.status("Validating and packaging the theme…")
    archive, warnings = build_archive(
        theme, root / "build" / "release", allow_remote_media=args.allow_remote_media
    )
    progress.done()
    _print_warnings(warnings)
    progress.status(f"Rendering {len(targets)} pages…")
    site = render_site(root, theme, targets)
    try:
        results = check_pages(site, targets, progress, expectations)
    finally:
        progress.done()
    write_gallery(site, theme.stem, targets, results)
    failures = [
        f"{target.label}: {message}"
        for target in targets
        for message in results.get(target.slug, [])
    ]
    passed = sum(not results.get(target.slug) for target in targets)
    report_path = root / "build" / "check-report.txt"
    if failures:
        report_path.write_text("FAIL\n" + "\n".join(failures) + "\n", encoding="utf-8")
    else:
        report_path.write_text(
            f"PASS\n{len(targets)} WebKit renders checked\nPackage: {archive.name}\n",
            encoding="utf-8",
        )
        print(f"PASS: {len(targets)} WebKit renders and {archive.name}")
    print(f"Preview: {site / 'index.html'}")
    _offer_to_open(site / "index.html", args.open)
    if failures:
        raise ThemeError(
            f"{len(targets) - passed} of {len(targets)} WebKit renders failed:\n- "
            + "\n- ".join(failures)
        )


def _project_mtime(root: Path) -> int:
    watched = [*root.glob("*.nnwtheme/*"), *root.glob("fixtures/*.toml")]
    return max((path.stat().st_mtime_ns for path in watched if path.is_file()), default=0)


def command_preview(args: argparse.Namespace) -> None:
    root = find_root()
    theme = find_theme(root)
    site = render_site(root, theme, normal_targets(extra_fixtures(root)))
    with serve(site) as url:
        print(f"Preview: {url}")
        if not args.no_open:
            webbrowser.open(url)
        previous = _project_mtime(root)
        print("Watching theme and fixtures. Press Ctrl-C to stop.")
        try:
            while True:
                time.sleep(1)
                current = _project_mtime(root)
                if current != previous:
                    render_site(root, theme, normal_targets(extra_fixtures(root)))
                    previous = current
                    print("Rebuilt preview.")
        except KeyboardInterrupt:
            print("\nPreview stopped.")


def _select_target(root: Path, args: argparse.Namespace) -> RenderTarget:
    targets = normal_targets(extra_fixtures(root))
    if args.fixture not in {target.fixture for target in targets}:
        raise ThemeError(f"unknown fixture: {args.fixture}")
    for target in targets:
        if (
            target.fixture == args.fixture
            and target.platform == args.platform
            and target.appearance == args.appearance
        ):
            return target
    raise ThemeError(f"{args.fixture} is checked on Mac and iPhone only")


def command_screenshot(args: argparse.Namespace) -> None:
    root = find_root()
    theme = find_theme(root)
    target = _select_target(root, args)
    site = render_site(root, theme, [target])
    expectations = _expectations(root, [target])
    failures = check_pages(site, [target], expectations=expectations)[target.slug]
    if failures:
        raise ThemeError("screenshot checks failed:\n- " + "\n- ".join(failures))
    source = site / "screenshots" / f"{target.slug}.png"
    print(source)
    if args.promote:
        destination = root / "screenshots" / "theme-preview.png"
        destination.parent.mkdir(exist_ok=True)
        shutil.copyfile(source, destination)
        print(f"Promoted marketplace screenshot: {destination}")


def command_capture(_args: argparse.Namespace) -> None:
    script = find_root() / "src" / "nnw_theme_tools" / "nnwdump.py"
    print(
        f"""Capture a real article as a fixture from a NetNewsWire debug build (needs Xcode).

1. Clone https://github.com/Ranchero-Software/NetNewsWire and open it in Xcode.
   In Shared/Article Rendering/ArticleRenderer.swift, set a breakpoint on the
   `return d` line at the end of articleSubstitutions(), then run the app.
2. Select the article to capture. When the breakpoint stops, load the command
   in the debugger console (once per debug session):

   command script import {script}

3. Write the fixture, then let the app continue:

   nnwdump fixtures/my-article.toml
   continue

4. Preview it with `uv run nnw-theme render my-article`.

nnwdump embeds the feed's real icon; pass --no-icon to keep the generated one.
A relative path is resolved against this repository, not the debugger's folder."""
    )


def command_bump(args: argparse.Namespace) -> None:
    root = find_root()
    theme = find_theme(root)
    metadata = read_plist(theme)
    current = metadata.get("Version")
    if not isinstance(current, int) or isinstance(current, bool):
        raise ThemeError("Info.plist Version must be an integer")
    proposed = current + 1
    if not args.yes and not _prompt_confirm(f"Increase Version from {current} to {proposed}?"):
        raise ThemeError("version bump cancelled")
    metadata["Version"] = proposed
    write_plist(theme / "Info.plist", metadata)
    print(f"Version is now {proposed}. Commit this change before publishing.")


def command_release_check(args: argparse.Namespace) -> None:
    root = find_root()
    theme = find_theme(root)
    current = read_plist(theme)
    previous_path = Path(args.previous_asset)
    with zipfile.ZipFile(previous_path) as archive:
        info_names = [name for name in archive.namelist() if name.endswith("/Info.plist")]
        if len(info_names) != 1:
            raise ThemeError("previous release must contain exactly one Info.plist")
        previous = plistlib.loads(archive.read(info_names[0]))
        old_bundle = info_names[0].split("/", 1)[0]
    if old_bundle != theme.name:
        raise ThemeError(f"bundle filename changed after release: {old_bundle} -> {theme.name}")
    if previous.get("ThemeIdentifier") != current.get("ThemeIdentifier"):
        raise ThemeError("ThemeIdentifier cannot change after the first release")
    if not isinstance(current.get("Version"), int) or current["Version"] <= previous.get(
        "Version", 0
    ):
        raise ThemeError("Info.plist Version must increase after the previous release")
    print(
        f"Release identity is stable and Version increases "
        f"{previous.get('Version')} -> {current['Version']}."
    )


def _add_common_remote_flag(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--allow-remote-media",
        action="store_true",
        help="acknowledge warnings for theme-owned remote fonts/images/media",
    )


def _command(
    commands: Any, name: str, summary: str, description: str | None = None
) -> argparse.ArgumentParser:
    return commands.add_parser(name, help=summary, description=description or summary)


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog="nnw-theme",
        description="Create, preview, check, and publish a NetNewsWire theme.",
        epilog="Run `nnw-theme COMMAND --help` for a command's options.",
    )
    commands = root.add_subparsers(
        dest="command", required=True, title="commands", metavar="COMMAND"
    )

    init = _command(
        commands,
        "init",
        "personalize a fresh copy of the template (run once)",
        "Name the theme, choose its permanent identifier, and optionally join the "
        "marketplace and install WebKit. Runs once, while .nnw-theme-uninitialized exists.",
    )
    init.add_argument("--name")
    init.add_argument("--creator")
    init.add_argument("--homepage")
    init.add_argument("--identifier")
    init.add_argument("--confirm-identifier")
    init.add_argument("--github-user")
    init.add_argument("--marketplace", choices=("yes", "no"))
    init.add_argument("--install-browser", action=argparse.BooleanOptionalAction, default=None)
    init.set_defaults(function=command_init)

    setup = _command(
        commands,
        "setup",
        "download NetNewsWire's rendering files and install WebKit",
        "Download the pinned NetNewsWire rendering files and install the WebKit browser "
        "that check and screenshot use. Safe to rerun.",
    )
    setup.set_defaults(function=command_setup)

    update_parser = _command(
        commands,
        "update",
        "refresh tooling and docs from the upstream template",
        "Replace this repository's tooling, tests, workflows, and agent guidance with the "
        "upstream template's. Your theme bundle and existing fixtures are never touched.",
    )
    update_parser.add_argument(
        "--ref", help="template branch, tag, or commit (default: newest release tag)"
    )
    update_parser.add_argument(
        "--dry-run", action="store_true", help="list the changes without writing them"
    )
    update_parser.set_defaults(
        function=lambda args: update(find_root(), args.ref, dry_run=args.dry_run)
    )

    preview = _command(
        commands,
        "preview",
        "live gallery for editing: serves, opens, and rebuilds on save",
        "Serve the preview gallery on localhost, open it, and rebuild whenever the theme "
        "or fixtures change. Pages render live in your own browser; nothing is checked. "
        "Runs until Ctrl-C.",
    )
    preview.add_argument("--no-open", action="store_true", help="do not open a browser")
    preview.set_defaults(function=command_preview)

    render = _command(
        commands,
        "render",
        "write the preview gallery once, without serving or checking",
        "Write the same gallery as preview to build/preview/ and exit. Useful for scripts "
        "and agents, since preview never exits.",
    )
    render.add_argument(
        "fixtures", nargs="*", help="fixtures to include (default: all), e.g. article"
    )
    render.set_defaults(function=command_render)

    check = _command(
        commands,
        "check",
        "release gate: package and test every case in WebKit",
        "Validate and package the theme, then render 16 cases (the article and "
        "kitchen-sink fixtures on Mac, iPhone, and iPad in light and dark, plus large "
        "text and Article JavaScript off) and four more for each fixture you add (Mac "
        "and iPhone, light and dark) in WebKit. Screenshot each, and fail on missing "
        "content, unresolved macros, overflow, broken images, footnotes that do not "
        "open, external requests, or JavaScript errors. Results go into the gallery in "
        "build/preview/.",
    )
    _add_common_remote_flag(check)
    check.add_argument(
        "--open",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="open the gallery when done (default: ask in a terminal)",
    )
    check.set_defaults(function=command_check)

    screenshot = _command(
        commands,
        "screenshot",
        "check one case in WebKit and save its image",
        "Render and check a single case in WebKit and save its full-page screenshot. "
        "With --promote, it becomes screenshots/theme-preview.png, the marketplace card.",
    )
    screenshot.add_argument("--fixture", default="article", help="fixture name")
    screenshot.add_argument("--platform", choices=("mac", "iphone", "ipad"), default="mac")
    screenshot.add_argument("--appearance", choices=("light", "dark"), default="light")
    screenshot.add_argument(
        "--promote", action="store_true", help="use it as the marketplace screenshot"
    )
    screenshot.set_defaults(function=command_screenshot)

    package = _command(
        commands,
        "package",
        "validate the theme and build its release ZIP (no WebKit)",
    )
    package.add_argument("--output-dir", default="dist")
    _add_common_remote_flag(package)
    package.set_defaults(function=command_package)

    capture = _command(
        commands,
        "capture",
        "explain how to capture a real article from NetNewsWire as a fixture",
    )
    capture.set_defaults(function=command_capture)

    bump = _command(commands, "bump", "increase the Info.plist Version before a release")
    bump.add_argument("--yes", action="store_true", help="skip the confirmation")
    bump.set_defaults(function=command_bump)

    marketplace = _command(commands, "marketplace", "manage marketplace participation")
    marketplace_commands = marketplace.add_subparsers(dest="marketplace_command", required=True)
    enable = marketplace_commands.add_parser("enable", help="add the discovery topic on GitHub")
    enable.set_defaults(function=lambda _args: marketplace_enable())

    # Used only by the Publish workflow. argparse cannot hide a subcommand (help=SUPPRESS
    # prints "==SUPPRESS=="), so it is added without help and dropped from the listing.
    release_check = commands.add_parser("release-check")
    release_check.add_argument("--previous-asset", required=True)
    release_check.set_defaults(function=command_release_check)
    commands._choices_actions = [
        action for action in commands._choices_actions if action.dest != "release-check"
    ]
    return root


def main() -> None:
    try:
        args = parser().parse_args()
        args.function(args)
    except ThemeError as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
