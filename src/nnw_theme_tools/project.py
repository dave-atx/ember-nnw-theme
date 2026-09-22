from __future__ import annotations

import plistlib
import tomllib
from pathlib import Path
from typing import Any

REQUIRED_THEME_FILES = ("Info.plist", "template.html", "stylesheet.css")
PLACEHOLDER_MARKER = ".nnw-theme-uninitialized"
IDENTITY_START = "<!-- nnw-theme-identity:start -->"
IDENTITY_END = "<!-- nnw-theme-identity:end -->"


class ThemeError(RuntimeError):
    """A user-actionable theme project error."""


def find_root(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    if current.is_file():
        current = current.parent
    for candidate in (current, *current.parents):
        if (candidate / "pyproject.toml").is_file() and (candidate / "fixtures").is_dir():
            return candidate
    raise ThemeError("run this command inside the theme repository")


def find_theme(root: Path) -> Path:
    themes = sorted(path for path in root.glob("*.nnwtheme") if path.is_dir())
    if len(themes) != 1:
        names = ", ".join(path.name for path in themes) or "none"
        raise ThemeError(
            f"expected one .nnwtheme directory at the repository root; found {names}"
        )
    return themes[0]


def read_plist(theme: Path) -> dict[str, Any]:
    path = theme / "Info.plist"
    try:
        with path.open("rb") as stream:
            value = plistlib.load(stream)
    except (OSError, plistlib.InvalidFileException) as error:
        raise ThemeError(f"{path}: invalid property list: {error}") from error
    if not isinstance(value, dict):
        raise ThemeError(f"{path}: the top-level value must be a dictionary")
    return value


def write_plist(path: Path, metadata: dict[str, Any]) -> None:
    with path.open("wb") as stream:
        plistlib.dump(metadata, stream, fmt=plistlib.FMT_XML, sort_keys=False)


def read_fixture(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as stream:
            value = tomllib.load(stream)
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ThemeError(f"{path}: invalid fixture: {error}") from error
    if not isinstance(value, dict):
        raise ThemeError(f"{path}: fixture must be a table")
    return value


def fixture_paths(root: Path, names: list[str] | None = None) -> list[Path]:
    if not names:
        paths = sorted((root / "fixtures").glob("*.toml"))
    else:
        paths = []
        for name in names:
            path = root / "fixtures" / (name if name.endswith(".toml") else f"{name}.toml")
            if not path.is_file():
                raise ThemeError(f"fixture not found: {path}")
            paths.append(path)
    if not paths:
        raise ThemeError("no fixtures found")
    return paths


def footnote_expectations(fixture: dict[str, Any], name: str) -> dict[str, Any]:
    """A fixture's optional [expect.footnotes] table, validated for the browser check.

    notes maps each footnote marker's rendered text to the note text its popover must
    show; plain_links lists CSS selectors for links that must not become footnotes;
    keep_with_word requires markers written against a word to stay on its line.
    """
    expect = fixture.get("expect", {})
    footnotes = expect.get("footnotes", {}) if isinstance(expect, dict) else None
    if not isinstance(footnotes, dict) or set(expect) - {"footnotes"}:
        raise ThemeError(f"{name}: [expect] may contain only a [expect.footnotes] table")
    if unknown := set(footnotes) - {"notes", "plain_links", "keep_with_word"}:
        raise ThemeError(
            f"{name}: unknown [expect.footnotes] key(s): {', '.join(sorted(unknown))}"
        )
    result: dict[str, Any] = {}
    if "notes" in footnotes:
        notes = footnotes["notes"]
        if not isinstance(notes, dict) or not all(
            isinstance(value, str) for value in notes.values()
        ):
            raise ThemeError(f"{name}: [expect.footnotes.notes] must map markers to text")
        result["notes"] = notes
    if "plain_links" in footnotes:
        links = footnotes["plain_links"]
        if not isinstance(links, list) or not all(isinstance(link, str) for link in links):
            raise ThemeError(f"{name}: expect.footnotes.plain_links must be CSS selectors")
        result["plain_links"] = links
    if "keep_with_word" in footnotes:
        if not isinstance(footnotes["keep_with_word"], bool):
            raise ThemeError(f"{name}: expect.footnotes.keep_with_word must be true or false")
        result["keep_with_word"] = footnotes["keep_with_word"]
    return result
