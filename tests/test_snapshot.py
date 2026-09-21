from __future__ import annotations

import hashlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nnw_theme_tools.project import ThemeError
from nnw_theme_tools.snapshot import ensure_snapshot

COMMIT = "1" * 40


def write_configuration(
    root: Path,
    content: bytes,
    *,
    sha256: str | None = None,
    destination: str = "Shared/core.css",
) -> None:
    digest = sha256 or hashlib.sha256(content).hexdigest()
    (root / "pyproject.toml").write_text(
        f'''[tool.nnw-theme.netnewswire]
release = "test-release"
commit = "{COMMIT}"

[[tool.nnw-theme.netnewswire.files]]
destination = "{destination}"
source = "Shared/Article Rendering/core.css"
sha256 = "{digest}"
''',
        encoding="utf-8",
    )


class SnapshotTests(unittest.TestCase):
    def test_downloads_verifies_and_reuses_cached_file(self) -> None:
        content = b"verified rendering input"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_configuration(root, content)
            with patch(
                "nnw_theme_tools.snapshot.urllib.request.urlopen",
                return_value=io.BytesIO(content),
            ) as urlopen:
                first = ensure_snapshot(root)
                second = ensure_snapshot(root)
            self.assertEqual(first.downloaded, ("Shared/core.css",))
            self.assertEqual(second.downloaded, ())
            self.assertEqual((first.path / "Shared" / "core.css").read_bytes(), content)
            self.assertEqual(urlopen.call_count, 1)
            requested_url = urlopen.call_args.args[0].full_url
            self.assertIn(COMMIT, requested_url)
            self.assertIn("Article%20Rendering", requested_url)

    def test_rejects_content_that_does_not_match_configured_hash(self) -> None:
        expected = b"expected"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_configuration(root, expected)
            with (
                patch(
                    "nnw_theme_tools.snapshot.urllib.request.urlopen",
                    return_value=io.BytesIO(b"changed upstream content"),
                ),
                self.assertRaisesRegex(ThemeError, "SHA-256 verification"),
            ):
                ensure_snapshot(root)
            cached = root / ".cache" / "netnewswire" / COMMIT / "Shared" / "core.css"
            self.assertFalse(cached.exists())

    def test_rejects_unsafe_configured_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_configuration(root, b"content", destination="../escape")
            with self.assertRaisesRegex(ThemeError, "unsafe path"):
                ensure_snapshot(root)


if __name__ == "__main__":
    unittest.main()
