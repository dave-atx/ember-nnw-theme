from __future__ import annotations

import io
import subprocess
import tarfile
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path, PurePosixPath
from unittest.mock import patch

from nnw_theme_tools.project import ThemeError
from nnw_theme_tools.update import latest_release, read_archive, update

COMMIT = "0123456789abcdef0123456789abcdef01234567"
README = "Intro\n<!-- nnw-theme-identity:start -->\n{}\n<!-- nnw-theme-identity:end -->\n{}\n"


def _archive(files: dict[str, str], links: dict[str, str] | None = None) -> bytes:
    data = io.BytesIO()
    with tarfile.open(
        fileobj=data, mode="w:gz", format=tarfile.PAX_FORMAT, pax_headers={"comment": COMMIT}
    ) as archive:
        for name, text in files.items():
            content = text.encode()
            member = tarfile.TarInfo(f"template-{COMMIT}/{name}")
            member.size = len(content)
            archive.addfile(member, io.BytesIO(content))
        for name, target in (links or {}).items():
            member = tarfile.TarInfo(f"template-{COMMIT}/{name}")
            member.type = tarfile.SYMTYPE
            member.linkname = target
            archive.addfile(member)
    return data.getvalue()


def _git(root: Path, *arguments: str) -> None:
    subprocess.run(["git", *arguments], cwd=root, check=True, capture_output=True)


class UpdateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        files = {
            "Mine.nnwtheme/stylesheet.css": "body { color: red; }\n",
            "src/nnw_theme_tools/cli.py": "old\n",
            "src/nnw_theme_tools/retired.py": "gone upstream\n",
            ".github/workflows/mine.yml": "theme workflow\n",
            "fixtures/article.toml": "customized\n",
            "pyproject.toml": "old\n",
            "README.md": README.format("# Mine", "Old docs."),
            ".gitignore": "build/\nnotes/\n",
        }
        for name, text in files.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        _git(self.root, "init")
        _git(self.root, "add", ".")
        _git(self.root, "-c", "user.name=T", "-c", "user.email=t@t", "commit", "-m", "base")
        self.upstream = read_archive(
            _archive(
                {
                    "Starter.nnwtheme/stylesheet.css": "starter\n",
                    "src/nnw_theme_tools/cli.py": "new\n",
                    ".github/workflows/check.yml": "check\n",
                    "fixtures/article.toml": "template fixture\n",
                    "fixtures/new.toml": "new fixture\n",
                    "pyproject.toml": "new\n",
                    "README.md": README.format("# Starter", "New docs."),
                    ".gitignore": "build/\n.cache/\n",
                    ".nnw-theme-uninitialized": "",
                },
                {".claude/skills/creating-nnw-themes": "../../.agents/skills/x"},
            )
        )

    def tearDown(self) -> None:
        self.directory.cleanup()

    def _update(self, *, dry_run: bool = False) -> str:
        output = io.StringIO()
        with (
            patch("nnw_theme_tools.update.download", return_value=self.upstream),
            redirect_stdout(output),
        ):
            update(self.root, "main", dry_run=dry_run)
        return output.getvalue()

    def test_latest_release_orders_versions_numerically(self) -> None:
        output = "".join(
            f"{COMMIT}\trefs/tags/{tag}\n"
            for tag in ("v1.0", "v1.9.0", "v1.10.0", "v2.0.0-rc.1", "theme-v9", "0.5.0")
        )
        self.assertEqual(latest_release(output), "v1.10.0")
        self.assertIsNone(latest_release(f"{COMMIT}\trefs/tags/v2.0.0-rc.1\n"))
        self.assertIsNone(latest_release(""))

    def test_defaults_to_newest_release(self) -> None:
        with (
            patch("nnw_theme_tools.update.default_ref", return_value="v1.0") as default,
            patch("nnw_theme_tools.update.download", return_value=self.upstream) as download,
            redirect_stdout(io.StringIO()) as output,
        ):
            update(self.root, None, dry_run=True)
        default.assert_called_once_with()
        download.assert_called_once_with("v1.0")
        self.assertIn(f"v1.0 ({COMMIT[:12]})", output.getvalue())

    def test_reads_commit_and_symlinks(self) -> None:
        commit, files = self.upstream
        self.assertEqual(commit, COMMIT)
        link = files[PurePosixPath(".claude/skills/creating-nnw-themes")]
        self.assertEqual(link.target, "../../.agents/skills/x")

    def test_updates_tooling_and_preserves_theme_files(self) -> None:
        self._update()
        root = self.root
        self.assertEqual((root / "src/nnw_theme_tools/cli.py").read_text(), "new\n")
        self.assertFalse((root / "src/nnw_theme_tools/retired.py").exists())
        self.assertEqual((root / ".github/workflows/mine.yml").read_text(), "theme workflow\n")
        self.assertEqual((root / ".github/workflows/check.yml").read_text(), "check\n")
        self.assertEqual((root / "fixtures/article.toml").read_text(), "customized\n")
        self.assertEqual((root / "fixtures/new.toml").read_text(), "new fixture\n")
        self.assertEqual((root / "README.md").read_text(), README.format("# Mine", "New docs."))
        self.assertEqual((root / ".gitignore").read_text(), "build/\nnotes/\n.cache/\n")
        self.assertTrue((root / ".claude/skills/creating-nnw-themes").is_symlink())
        self.assertTrue((root / "Mine.nnwtheme/stylesheet.css").is_file())
        self.assertFalse((root / "Starter.nnwtheme").exists())
        self.assertFalse((root / ".nnw-theme-uninitialized").exists())
        _git(root, "add", "-A")
        _git(root, "-c", "user.name=T", "-c", "user.email=t@t", "commit", "-m", "update")
        self.assertIn("already matches", self._update())

    def test_readme_without_template_docs_is_kept(self) -> None:
        readme = "<!-- nnw-theme-identity:start -->\n# Mine\n\nAll mine.\n"
        readme += "<!-- nnw-theme-identity:end -->\n"
        (self.root / "README.md").write_text(readme)
        _git(self.root, "commit", "-qam", "own readme", "--author=T <t@t>")
        self._update()
        self.assertEqual((self.root / "README.md").read_text(), readme)

    def test_dry_run_writes_nothing(self) -> None:
        output = self._update(dry_run=True)
        self.assertIn("Would update", output)
        self.assertEqual((self.root / "src/nnw_theme_tools/cli.py").read_text(), "old\n")

    def test_refuses_uncommitted_template_changes(self) -> None:
        (self.root / "pyproject.toml").write_text("local edit\n")
        with self.assertRaisesRegex(ThemeError, "commit your changes"):
            self._update()
        self.assertEqual((self.root / "src/nnw_theme_tools/cli.py").read_text(), "old\n")

    def test_refuses_uninitialized_repository(self) -> None:
        (self.root / ".nnw-theme-uninitialized").touch()
        with self.assertRaisesRegex(ThemeError, "initialize"):
            self._update()


if __name__ == "__main__":
    unittest.main()
