from __future__ import annotations

import argparse
import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from nnw_theme_tools.cli import (
    _absolute_homepage,
    _CheckProgress,
    _offer_to_open,
    command_init,
    parser,
)
from nnw_theme_tools.project import PLACEHOLDER_MARKER, ThemeError, write_plist
from nnw_theme_tools.render import normal_targets


def _template(root: Path) -> Path:
    theme = root / "Starter.nnwtheme"
    theme.mkdir()
    write_plist(
        theme / "Info.plist",
        {
            "ThemeIdentifier": "com.example.starter",
            "Name": "Starter",
            "CreatorHomePage": "https://example.com",
            "CreatorName": "Theme Author",
            "Version": 1,
        },
    )
    (root / "README.md").write_text(
        "<!-- nnw-theme-identity:start -->\nold\n"
        "<!-- nnw-theme-identity:end -->\n\nKept documentation.\n",
        encoding="utf-8",
    )
    (root / "screenshots").mkdir()
    (root / "screenshots" / "theme-preview.png").write_bytes(b"template image")
    (root / PLACEHOLDER_MARKER).touch()
    return theme


def _init_args(*, install_browser: bool) -> argparse.Namespace:
    return argparse.Namespace(
        name="Quiet Reader",
        creator="Theme Author",
        homepage="https://github.com/theme-author",
        github_user="theme-author",
        identifier="io.github.theme-author.quiet-reader",
        confirm_identifier="io.github.theme-author.quiet-reader",
        marketplace="no",
        install_browser=install_browser,
    )


class InitTests(unittest.TestCase):
    def test_rejects_placeholder_homepage(self) -> None:
        with self.assertRaisesRegex(ThemeError, "placeholder"):
            _absolute_homepage("https://example.com")

    def test_initialization_removes_starter_screenshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            theme = _template(root)

            with (
                patch("nnw_theme_tools.cli.find_root", return_value=root),
                patch("nnw_theme_tools.cli.find_theme", return_value=theme),
                redirect_stdout(io.StringIO()),
            ):
                command_init(_init_args(install_browser=False))

            self.assertFalse((root / "screenshots" / "theme-preview.png").exists())
            self.assertFalse((root / PLACEHOLDER_MARKER).exists())
            self.assertTrue((root / "Quiet Reader.nnwtheme").is_dir())
            self.assertIn("Kept documentation.", (root / "README.md").read_text())

    def test_preview_setup_failure_does_not_fail_initialization(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            theme = _template(root)
            stderr = io.StringIO()

            with (
                patch("nnw_theme_tools.cli.find_root", return_value=root),
                patch("nnw_theme_tools.cli.find_theme", return_value=theme),
                patch(
                    "nnw_theme_tools.cli.ensure_snapshot",
                    side_effect=ThemeError("install playwright-cli first"),
                ),
                redirect_stdout(io.StringIO()),
                redirect_stderr(stderr),
            ):
                command_init(_init_args(install_browser=True))

            self.assertFalse((root / PLACEHOLDER_MARKER).exists())
            self.assertIn("install playwright-cli first", stderr.getvalue())
            self.assertIn("uv run nnw-theme setup", stderr.getvalue())


class HelpTests(unittest.TestCase):
    def test_release_check_is_hidden_but_still_parses(self) -> None:
        text = parser().format_help()
        self.assertNotIn("release-check", text)
        self.assertNotIn("SUPPRESS", text)
        args = parser().parse_args(["release-check", "--previous-asset", "old.zip"])
        self.assertEqual(args.previous_asset, "old.zip")


class _Terminal(io.StringIO):
    def isatty(self) -> bool:
        return True


class CheckOutputTests(unittest.TestCase):
    def test_plain_progress_prints_one_line_per_case(self) -> None:
        stream = io.StringIO()
        progress = _CheckProgress(2, stream)
        first, second = normal_targets()[:2]
        progress.start(1, first)
        progress.finish(1, first, [])
        progress.start(2, second)
        progress.finish(2, second, ["horizontal document overflow"])
        progress.done()
        self.assertEqual(
            stream.getvalue(),
            "[1/2] Article · Mac · light … passed\n"
            "[2/2] Article · Mac · dark … FAILED: horizontal document overflow\n",
        )

    def test_terminal_progress_rewrites_one_line_and_keeps_failures(self) -> None:
        stream = _Terminal()
        progress = _CheckProgress(2, stream)
        first, second = normal_targets()[:2]
        progress.start(1, first)
        progress.finish(1, first, [])
        progress.start(2, second)
        progress.finish(2, second, ["page errors"])
        progress.done()
        output = stream.getvalue()
        self.assertIn("\r\033[KChecking 1/2 · Article · Mac · light", output)
        self.assertIn("\r\033[K✗ Article · Mac · dark: page errors\n", output)
        self.assertTrue(output.endswith("\r\033[K"))
        self.assertEqual(output.count("\n"), 1)

    def test_open_choice_overrides_the_prompt(self) -> None:
        index = Path("/tmp/preview/index.html")
        with (
            patch("nnw_theme_tools.cli.webbrowser.open") as browser,
            patch("nnw_theme_tools.cli._prompt_confirm") as prompt,
        ):
            _offer_to_open(index, True)
            _offer_to_open(index, False)
        browser.assert_called_once_with(index.as_uri())
        prompt.assert_not_called()

    def test_open_is_not_offered_outside_a_terminal(self) -> None:
        with (
            patch("nnw_theme_tools.cli.sys.stdin", io.StringIO()),
            patch("nnw_theme_tools.cli.webbrowser.open") as browser,
            patch("nnw_theme_tools.cli._prompt_confirm") as prompt,
        ):
            _offer_to_open(Path("/tmp/preview/index.html"), None)
        browser.assert_not_called()
        prompt.assert_not_called()


if __name__ == "__main__":
    unittest.main()
