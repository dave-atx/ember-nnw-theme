from __future__ import annotations

import io
import plistlib
import stat
import tempfile
import unittest
import warnings
import zipfile
from pathlib import Path

from nnw_theme_tools.package import archive_bytes
from nnw_theme_tools.validate import validate_archive, validate_source


def metadata(name: str = "Reader") -> dict[str, object]:
    return {
        "ThemeIdentifier": "org.example.reader",
        "Name": name,
        "CreatorHomePage": "https://author.example.org",
        "CreatorName": "A. Reader",
        "Version": 1,
    }


def make_theme(parent: Path, name: str = "Reader") -> Path:
    theme = parent / f"{name}.nnwtheme"
    theme.mkdir()
    (theme / "Info.plist").write_bytes(plistlib.dumps(metadata(name)))
    (theme / "template.html").write_text(
        '<main class="articleBody">[[body]]</main>', encoding="utf-8"
    )
    (theme / "stylesheet.css").write_text("body { color: CanvasText; }", encoding="utf-8")
    return theme


class SourceValidationTests(unittest.TestCase):
    def test_valid_minimal_theme(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report = validate_source(make_theme(Path(directory)))
            self.assertEqual(report.errors, [])

    def test_rejects_wrong_case_required_file_and_extra_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            theme = make_theme(Path(directory))
            (theme / "Info.plist").rename(theme / "info.plist")
            (theme / "image.png").write_bytes(b"image")
            report = validate_source(theme)
            self.assertTrue(any("Info.plist" in error for error in report.errors))
            self.assertTrue(any("image.png" in error for error in report.errors))

    def test_rejects_bad_homepage_and_name_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            theme = make_theme(Path(directory))
            value = metadata("Different")
            value["CreatorHomePage"] = "javascript:alert(1)"
            (theme / "Info.plist").write_bytes(plistlib.dumps(value))
            report = validate_source(theme)
            self.assertTrue(any("must match" in error for error in report.errors))
            self.assertTrue(any("HTTP(S)" in error for error in report.errors))

    def test_remote_media_needs_explicit_override_but_script_is_always_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            theme = make_theme(Path(directory))
            (theme / "template.html").write_text(
                '<main class="articleBody">[[body]]<img src="https://img.example/a.png">'
                '<script src="https://js.example/a.js"></script></main>',
                encoding="utf-8",
            )
            blocked = validate_source(theme)
            allowed = validate_source(theme, allow_remote_media=True)
            self.assertGreaterEqual(len(blocked.errors), 2)
            self.assertTrue(any("external script" in error for error in allowed.errors))
            self.assertTrue(
                any("remote theme-owned" in warning for warning in allowed.warnings)
            )

    def test_protocol_relative_media_is_remote(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            theme = make_theme(Path(directory))
            (theme / "template.html").write_text(
                '<main class="articleBody">[[body]]<img src="//img.example/a.png"></main>',
                encoding="utf-8",
            )
            self.assertTrue(any("remote" in error for error in validate_source(theme).errors))

    def test_rejects_fake_bundle_local_resource(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            theme = make_theme(Path(directory))
            (theme / "stylesheet.css").write_text(
                "body { background: url(background.png); }", encoding="utf-8"
            )
            self.assertTrue(
                any("bundle-local" in error for error in validate_source(theme).errors)
            )


class ArchiveValidationTests(unittest.TestCase):
    def test_package_is_deterministic_and_valid(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            theme = make_theme(Path(directory))
            first, warnings = archive_bytes(theme)
            second, _ = archive_bytes(theme)
            self.assertEqual(first, second)
            self.assertEqual(warnings, [])
            self.assertEqual(validate_archive(first, "Reader.nnwtheme.zip").errors, [])

    def test_rejects_traversal(self) -> None:
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            archive.writestr("Reader.nnwtheme/../Info.plist", b"bad")
        report = validate_archive(output.getvalue(), "Reader.nnwtheme.zip")
        self.assertTrue(any("unsafe path" in error for error in report.errors))

    def test_rejects_symlink(self) -> None:
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            info = zipfile.ZipInfo("Reader.nnwtheme/Info.plist")
            info.create_system = 3
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(info, "elsewhere")
        report = validate_archive(output.getvalue(), "Reader.nnwtheme.zip")
        self.assertTrue(any("symbolic link" in error for error in report.errors))

    def test_rejects_duplicate_archive_paths(self) -> None:
        output = io.BytesIO()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with zipfile.ZipFile(output, "w") as archive:
                archive.writestr("Reader.nnwtheme/Info.plist", plistlib.dumps(metadata()))
                archive.writestr("Reader.nnwtheme/Info.plist", plistlib.dumps(metadata()))
        report = validate_archive(output.getvalue(), "Reader.nnwtheme.zip")
        self.assertTrue(any("duplicate paths" in error for error in report.errors))


if __name__ == "__main__":
    unittest.main()
