from __future__ import annotations

import io
import plistlib
import re
import stat
import zipfile
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlparse

from .project import (
    PLACEHOLDER_MARKER,
    REQUIRED_THEME_FILES,
    ThemeError,
    read_plist,
)

MAX_ASSET_BYTES = 25 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 50 * 1024 * 1024
REQUIRED_PLIST_FIELDS: dict[str, type] = {
    "ThemeIdentifier": str,
    "Name": str,
    "CreatorHomePage": str,
    "CreatorName": str,
    "Version": int,
}
PLACEHOLDERS = ("starter", "example.com", "your name", "change me", "todo")
SAFE_BUNDLE_NAME = re.compile(r"^[^/\\\0]+$")
OPTIONAL_THEME_FILE = re.compile(r"^(?:LICENSE|NOTICE)(?:\.[A-Za-z0-9-]+)?$")


@dataclass
class ValidationReport:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def require_ok(self) -> None:
        if self.errors:
            raise ThemeError("theme validation failed:\n- " + "\n- ".join(self.errors))


class _ResourceParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.references: list[tuple[str, str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {name.lower(): value or "" for name, value in attrs}
        tag = tag.lower()
        if tag == "link" and values.get("rel", "").lower() == "stylesheet":
            self.references.append(("stylesheet", "href", values.get("href", "")))
        for attribute in ("src", "poster"):
            if attribute in values:
                self.references.append((tag, attribute, values[attribute]))


def _is_remote(value: str) -> bool:
    return value.startswith("//") or urlparse(value).scheme.lower() in {"http", "https"}


def _is_allowed_file(name: str) -> bool:
    return name in REQUIRED_THEME_FILES or bool(OPTIONAL_THEME_FILE.fullmatch(name.upper()))


def validate_metadata(metadata: dict[str, Any], bundle_stem: str) -> ValidationReport:
    report = ValidationReport()
    for field_name, field_type in REQUIRED_PLIST_FIELDS.items():
        value = metadata.get(field_name)
        valid = isinstance(value, field_type) and not (
            field_type is int and isinstance(value, bool)
        )
        if not valid or (isinstance(value, str) and not value.strip()):
            report.errors.append(
                f"Info.plist: {field_name} must be a non-empty {field_type.__name__}"
            )
    if report.errors:
        return report

    if metadata["Name"] != bundle_stem:
        report.errors.append(
            f"Info.plist Name ({metadata['Name']!r}) must match bundle name ({bundle_stem!r})"
        )
    home = urlparse(metadata["CreatorHomePage"])
    if home.scheme not in {"http", "https"} or not home.netloc:
        report.errors.append("Info.plist CreatorHomePage must be an absolute HTTP(S) URL")
    for field_name in ("ThemeIdentifier", "Name", "CreatorHomePage", "CreatorName"):
        lowered = metadata[field_name].strip().lower()
        if any(token in lowered for token in PLACEHOLDERS):
            report.errors.append(f"Info.plist {field_name} still contains placeholder metadata")
    if metadata["Version"] < 1:
        report.errors.append("Info.plist Version must be an integer of at least 1")
    return report


def validate_source(theme: Path, *, allow_remote_media: bool = False) -> ValidationReport:
    report = ValidationReport()
    if not SAFE_BUNDLE_NAME.fullmatch(theme.stem) or theme.stem in {".", ".."}:
        report.errors.append("theme bundle name contains path-unsafe characters")
    if (theme.parent / PLACEHOLDER_MARKER).exists():
        report.errors.append("run `uv run nnw-theme init` before packaging this theme")

    actual = {path.name for path in theme.iterdir()}
    for required in REQUIRED_THEME_FILES:
        if required not in actual:
            report.errors.append(f"theme is missing exact required file {required}")
    for path in theme.iterdir():
        if path.is_symlink():
            report.errors.append(f"theme contains symbolic link {path.name}")
        elif not path.is_file():
            report.errors.append(f"theme contains unsupported directory {path.name}")
        elif not _is_allowed_file(path.name):
            report.errors.append(f"theme contains unsupported file {path.name}")
    if report.errors and "Info.plist" not in actual:
        return report

    metadata_report = validate_metadata(read_plist(theme), theme.stem)
    report.errors.extend(metadata_report.errors)
    report.warnings.extend(metadata_report.warnings)

    template_path = theme / "template.html"
    if template_path.is_file():
        parser = _ResourceParser()
        template = template_path.read_text(encoding="utf-8")
        if "[[" not in template:
            report.warnings.append("template.html contains no NetNewsWire macros")
        parser.feed(template)
        if re.search(r"<style\b[^>]*>.*?@import\s", template, re.DOTALL | re.IGNORECASE):
            report.errors.append("CSS @import is not allowed in template.html")
        for tag, attribute, value in parser.references:
            if not value or value.startswith(("data:", "#", "mailto:", "tel:")):
                continue
            if tag in {"script", "stylesheet"}:
                report.errors.append(f"external {tag} is not allowed: {value}")
            elif _is_remote(value):
                message = f"remote theme-owned {tag} may not load in NetNewsWire: {value}"
                if allow_remote_media:
                    report.warnings.append(message)
                else:
                    report.errors.append(
                        message + " (pass --allow-remote-media to acknowledge)"
                    )
            elif "[[" not in value:
                report.errors.append(
                    "bundle-local resource references do not work in NetNewsWire: "
                    f"{attribute}={value!r}"
                )

    stylesheet_path = theme / "stylesheet.css"
    if stylesheet_path.is_file():
        css = stylesheet_path.read_text(encoding="utf-8")
        for value in re.findall(r"url\(\s*['\"]?([^)'\"]+)", css, flags=re.IGNORECASE):
            value = value.strip()
            if value.startswith("data:"):
                continue
            if _is_remote(value):
                message = f"remote CSS resource may not load in NetNewsWire: {value}"
                if allow_remote_media:
                    report.warnings.append(message)
                else:
                    report.errors.append(
                        message + " (pass --allow-remote-media to acknowledge)"
                    )
            else:
                report.errors.append(
                    f"bundle-local CSS resource does not work in NetNewsWire: {value}"
                )
        if re.search(r"@import\s", css, flags=re.IGNORECASE):
            report.errors.append("CSS @import is not allowed")
    return report


def validate_archive(content: bytes, asset_name: str) -> ValidationReport:
    report = ValidationReport()
    if not asset_name.endswith(".nnwtheme.zip"):
        # Everything below derives the bundle name from this suffix.
        report.errors.append("release asset name must end in .nnwtheme.zip")
        return report
    if len(content) > MAX_ASSET_BYTES:
        report.errors.append("release asset exceeds the 25 MiB compressed limit")
        return report
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            infos = archive.infolist()
            if sum(info.file_size for info in infos) > MAX_UNCOMPRESSED_BYTES:
                report.errors.append("release asset exceeds the 50 MiB expanded limit")
            if any(stat.S_ISLNK(info.external_attr >> 16) for info in infos):
                report.errors.append("release asset contains a symbolic link")
            paths = [PurePosixPath(info.filename) for info in infos if not info.is_dir()]
            if len(paths) != len(set(paths)):
                report.errors.append("release asset contains duplicate paths")
            if any(path.is_absolute() or ".." in path.parts for path in paths):
                report.errors.append("release asset contains an unsafe path")
                return report
            roots = {
                path.parts[0]
                for path in paths
                if path.parts and path.parts[0].endswith(".nnwtheme")
            }
            expected_stem = asset_name.removesuffix(".nnwtheme.zip")
            expected_root = f"{expected_stem}.nnwtheme"
            if roots != {expected_root}:
                report.errors.append(
                    f"archive must contain exactly one top-level {expected_root} bundle"
                )
                return report
            names = {path.as_posix() for path in paths}
            for required in REQUIRED_THEME_FILES:
                if f"{expected_root}/{required}" not in names:
                    report.errors.append(f"archive is missing exact required file {required}")
            for path in paths:
                if len(path.parts) != 2 or not _is_allowed_file(path.name):
                    report.errors.append(f"archive contains unsupported path {path.as_posix()}")
            if not report.errors:
                metadata = plistlib.loads(archive.read(f"{expected_root}/Info.plist"))
                metadata_report = validate_metadata(metadata, expected_stem)
                report.errors.extend(metadata_report.errors)
    except (zipfile.BadZipFile, plistlib.InvalidFileException, KeyError) as error:
        report.errors.append(f"invalid theme archive: {error}")
    return report
