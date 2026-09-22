from __future__ import annotations

import io
import re
import subprocess
import sys
import tarfile
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from .project import IDENTITY_END, IDENTITY_START, PLACEHOLDER_MARKER, ThemeError

UPSTREAM = "dave-atx/netnewswire-theme-template"
# Release tags look like v1.0 or v1.2.3; pre-release suffixes (v2.0.0-rc.1) are skipped.
RELEASE_TAG = re.compile(r"v?(\d+)\.(\d+)(?:\.(\d+))?")
MAX_ARCHIVE_BYTES = 20 * 1024 * 1024

# Template-owned directories are mirrored: upstream deletions are removed locally too.
MIRRORED_DIRECTORIES = (
    "src/nnw_theme_tools",
    "tests",
    ".agents/skills/creating-nnw-themes",
)
# Theme repositories may add workflows of their own, so .github is only added to.
MERGED_DIRECTORIES = (".github",)
TEMPLATE_FILES = (
    ".claude/skills/creating-nnw-themes",
    ".python-version",
    "AGENTS.md",
    "CLAUDE.md",
    "THIRD_PARTY_NOTICES.md",
    "pyproject.toml",
    "uv.lock",
)


@dataclass(frozen=True)
class Entry:
    """A regular file (content) or a symbolic link (target) from the upstream archive."""

    content: bytes | None = None
    target: str | None = None


@dataclass
class Plan:
    writes: dict[PurePosixPath, Entry] = field(default_factory=dict)
    removals: list[PurePosixPath] = field(default_factory=list)
    kept_fixtures: list[PurePosixPath] = field(default_factory=list)


def latest_release(ls_remote_output: str) -> str | None:
    """The highest release tag in `git ls-remote --tags` output, if any."""
    releases: list[tuple[tuple[int, int, int], str]] = []
    for line in ls_remote_output.splitlines():
        _, _, ref = line.partition("\t")
        tag = ref.removeprefix("refs/tags/")
        if match := RELEASE_TAG.fullmatch(tag):
            major, minor, patch = match.groups()
            releases.append(((int(major), int(minor), int(patch or 0)), tag))
    return max(releases)[1] if releases else None


def default_ref() -> str:
    """The newest upstream release tag, or main until the template has one."""
    try:
        result = subprocess.run(
            ["git", "ls-remote", "--tags", "--refs", f"https://github.com/{UPSTREAM}.git"],
            capture_output=True,
            text=True,
            check=True,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise ThemeError(f"could not list template releases: {error}") from error
    if tag := latest_release(result.stdout):
        return tag
    print("The template has no release tags yet; using its main branch.", file=sys.stderr)
    return "main"


def download(ref: str) -> tuple[str, dict[PurePosixPath, Entry]]:
    """The upstream commit SHA and its files, from GitHub's source tarball."""
    url = f"https://codeload.github.com/{UPSTREAM}/tar.gz/{urllib.parse.quote(ref, safe='')}"
    request = urllib.request.Request(url, headers={"User-Agent": "nnw-theme-tools"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            data = response.read(MAX_ARCHIVE_BYTES + 1)
    except (OSError, urllib.error.URLError) as error:
        raise ThemeError(f"could not download the template at {ref!r}: {error}") from error
    if len(data) > MAX_ARCHIVE_BYTES:
        raise ThemeError("the template archive exceeds the size limit")
    return read_archive(data)


def read_archive(data: bytes) -> tuple[str, dict[PurePosixPath, Entry]]:
    files: dict[PurePosixPath, Entry] = {}
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
        commit = archive.pax_headers.get("comment", "")
        for member in archive.getmembers():
            parts = PurePosixPath(member.name).parts[1:]  # drop "<repo>-<ref>/"
            if not parts or member.isdir():
                continue
            if PurePosixPath(member.name).is_absolute() or ".." in parts:
                raise ThemeError(f"the template archive contains an unsafe path: {member.name}")
            path = PurePosixPath(*parts)
            if member.issym():
                files[path] = Entry(target=member.linkname)
            elif member.isfile():
                stream = archive.extractfile(member)
                if stream is None:
                    continue
                files[path] = Entry(content=stream.read())
    if not files:
        raise ThemeError("the template archive is empty")
    return commit, files


def _local(path: Path) -> Entry | None:
    if path.is_symlink():
        return Entry(target=str(path.readlink()))
    if path.is_file():
        return Entry(content=path.read_bytes())
    return None


def _merge_readme(local: str, upstream: str) -> str:
    """Upstream documentation around this theme's own identity block.

    A README that ends with its identity block has dropped the template's
    documentation on purpose, so it is kept as it is.
    """
    start, end = local.find(IDENTITY_START), local.find(IDENTITY_END)
    upstream_start, upstream_end = upstream.find(IDENTITY_START), upstream.find(IDENTITY_END)
    if min(start, end, upstream_start, upstream_end) < 0:
        raise ThemeError("README identity markers are missing")
    if not local[end + len(IDENTITY_END) :].strip():
        return local
    identity = local[start : end + len(IDENTITY_END)]
    return upstream[:upstream_start] + identity + upstream[upstream_end + len(IDENTITY_END) :]


def _merge_gitignore(local: str, upstream: str) -> str:
    present = set(local.splitlines())
    missing = [line for line in upstream.splitlines() if line and line not in present]
    if not missing:
        return local
    separator = "" if not local or local.endswith("\n") else "\n"
    return local + separator + "\n".join(missing) + "\n"


def plan_update(root: Path, upstream: dict[PurePosixPath, Entry]) -> Plan:
    plan = Plan()

    def propose(path: PurePosixPath, entry: Entry) -> None:
        if _local(root / path) != entry:
            plan.writes[path] = entry

    for directory in (*MIRRORED_DIRECTORIES, *MERGED_DIRECTORIES):
        prefix = PurePosixPath(directory)
        for path, entry in upstream.items():
            if path.is_relative_to(prefix):
                propose(path, entry)
        if directory in MIRRORED_DIRECTORIES and (root / prefix).is_dir():
            for local in sorted((root / prefix).rglob("*")):
                relative = PurePosixPath(local.relative_to(root).as_posix())
                if "__pycache__" in relative.parts or local.is_dir():
                    continue
                if relative not in upstream:
                    plan.removals.append(relative)
    for name in TEMPLATE_FILES:
        path = PurePosixPath(name)
        if path in upstream:
            propose(path, upstream[path])

    for path, entry in upstream.items():
        if path.parent == PurePosixPath("fixtures") and entry.content is not None:
            if (root / path).exists():
                if _local(root / path) != entry:
                    plan.kept_fixtures.append(path)
            else:
                plan.writes[path] = entry

    for name, merge in (("README.md", _merge_readme), (".gitignore", _merge_gitignore)):
        path = PurePosixPath(name)
        if path in upstream and upstream[path].content is not None:
            local = (root / path).read_text(encoding="utf-8") if (root / path).is_file() else ""
            merged = merge(local, upstream[path].content.decode("utf-8"))
            propose(path, Entry(content=merged.encode("utf-8")))
    return plan


def _require_clean(root: Path, plan: Plan) -> None:
    paths = [path.as_posix() for path in (*plan.writes, *plan.removals)]
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain", "--", *paths],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        message = "update needs a Git repository so its changes can be reviewed"
        raise ThemeError(message) from error
    if result.stdout.strip():
        raise ThemeError(
            # Not "or stash": a plain stash leaves untracked files behind, which splits an
            # uncommitted init into a new bundle beside a restored Starter.nnwtheme.
            "commit your changes to these files before updating:\n" + result.stdout.rstrip()
        )


def apply_plan(root: Path, plan: Plan) -> None:
    for path, entry in plan.writes.items():
        destination = root / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.is_symlink() or destination.is_file():
            destination.unlink()
        if entry.target is not None:
            destination.symlink_to(entry.target)
        else:
            destination.write_bytes(entry.content or b"")
    for path in plan.removals:
        (root / path).unlink()


def update(root: Path, ref: str | None, *, dry_run: bool) -> None:
    if (root / PLACEHOLDER_MARKER).exists():
        raise ThemeError("initialize this theme with `uv run nnw-theme init` before updating")
    ref = ref or default_ref()
    commit, upstream = download(ref)
    plan = plan_update(root, upstream)
    label = f"{ref} ({commit[:12]})" if commit else ref
    if not plan.writes and not plan.removals:
        print(f"Template tooling already matches {label}.")
    else:
        changes = [
            f"  {'M' if (root / path).exists() or (root / path).is_symlink() else '+'} {path}"
            for path in sorted(plan.writes)
        ] + [f"  - {path}" for path in plan.removals]
        if not dry_run:
            _require_clean(root, plan)
            apply_plan(root, plan)
        print(f"{'Would update' if dry_run else 'Updated'} template tooling to {label}:")
        print("\n".join(changes))
    for path in plan.kept_fixtures:
        print(f"Kept your {path}; it differs from the template's copy.")
    if plan.writes and not dry_run:
        print("Review with `git diff`, run `uv run nnw-theme check`, then commit.")
