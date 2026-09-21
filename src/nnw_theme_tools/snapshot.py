from __future__ import annotations

import hashlib
import re
import tempfile
import tomllib
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from .project import ThemeError

RAW_ROOT = "https://raw.githubusercontent.com/Ranchero-Software/NetNewsWire"
MAX_FILE_BYTES = 2 * 1024 * 1024


@dataclass(frozen=True)
class Snapshot:
    path: Path
    release: str
    commit: str
    downloaded: tuple[str, ...]


def _safe_relative_path(value: object, field: str) -> PurePosixPath:
    if not isinstance(value, str) or not value:
        raise ThemeError(f"snapshot configuration {field} must be a non-empty string")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ThemeError(f"snapshot configuration {field} contains an unsafe path")
    return path


def _configuration(
    root: Path,
) -> tuple[str, str, dict[PurePosixPath, tuple[PurePosixPath, str]]]:
    path = root / "pyproject.toml"
    try:
        with path.open("rb") as stream:
            project: Any = tomllib.load(stream)
        value = project["tool"]["nnw-theme"]["netnewswire"]
    except (OSError, tomllib.TOMLDecodeError, KeyError, TypeError) as error:
        message = f"{path}: invalid NetNewsWire snapshot configuration: {error}"
        raise ThemeError(message) from error
    if not isinstance(value, dict):
        raise ThemeError(f"{path}: NetNewsWire snapshot configuration must be a table")
    release = value.get("release")
    commit = value.get("commit")
    files = value.get("files")
    if not isinstance(release, str) or not release:
        raise ThemeError(f"{path}: release must be a non-empty string")
    if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ThemeError(f"{path}: commit must be a full lowercase Git SHA")
    if not isinstance(files, list) or not files:
        raise ThemeError(f"{path}: files must be a non-empty array of tables")

    parsed: dict[PurePosixPath, tuple[PurePosixPath, str]] = {}
    for details in files:
        if not isinstance(details, dict):
            raise ThemeError(f"{path}: each file must be a table")
        destination = _safe_relative_path(details.get("destination"), "destination")
        if destination in parsed:
            raise ThemeError(f"{path}: duplicate destination {destination}")
        source = _safe_relative_path(details.get("source"), f"source for {destination}")
        sha256 = details.get("sha256")
        if not isinstance(sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", sha256):
            raise ThemeError(f"{path}: sha256 for {destination} is invalid")
        parsed[destination] = (source, sha256)
    return release, commit, parsed


def _matches(path: Path, expected_sha256: str) -> bool:
    if not path.is_file() or path.is_symlink():
        return False
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            while chunk := stream.read(64 * 1024):
                digest.update(chunk)
    except OSError:
        return False
    return digest.hexdigest() == expected_sha256


def _download(url: str, expected_sha256: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "nnw-theme-tools"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            content = response.read(MAX_FILE_BYTES + 1)
    except (OSError, urllib.error.URLError) as error:
        raise ThemeError(
            f"could not download pinned NetNewsWire input {url}: {error}"
        ) from error
    if len(content) > MAX_FILE_BYTES:
        raise ThemeError(f"pinned NetNewsWire input exceeds the size limit: {url}")
    actual = hashlib.sha256(content).hexdigest()
    if actual != expected_sha256:
        raise ThemeError(
            f"pinned NetNewsWire input failed SHA-256 verification: {url} "
            f"(expected {expected_sha256}, received {actual})"
        )
    return content


def _write_atomic(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=path.parent, prefix=f".{path.name}.", delete=False
        ) as stream:
            temporary_name = stream.name
            stream.write(content)
        Path(temporary_name).replace(path)
    finally:
        if temporary_name:
            Path(temporary_name).unlink(missing_ok=True)


def ensure_snapshot(root: Path) -> Snapshot:
    release, commit, files = _configuration(root)
    cache = root / ".cache" / "netnewswire" / commit
    downloaded: list[str] = []
    for destination, (source, sha256) in files.items():
        cached_file = cache.joinpath(*destination.parts)
        if _matches(cached_file, sha256):
            continue
        encoded_source = urllib.parse.quote(source.as_posix(), safe="/")
        url = f"{RAW_ROOT}/{commit}/{encoded_source}"
        _write_atomic(cached_file, _download(url, sha256))
        downloaded.append(destination.as_posix())
    return Snapshot(cache, release, commit, tuple(downloaded))
