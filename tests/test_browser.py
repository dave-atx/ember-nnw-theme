from __future__ import annotations

import io
import subprocess
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from nnw_theme_tools.browser import FOOTNOTE_CHECK, _failures, _javascript, setup_webkit
from nnw_theme_tools.render import normal_targets

PASSING = {
    "article": True,
    "textLength": 100,
    "unresolved": False,
    "overflow": False,
    "brokenImages": [],
    "footnotes": [],
    "blocked": [],
    "pageErrors": [],
}


class CheckScriptTests(unittest.TestCase):
    def test_footnote_check_runs_last_with_the_fixture_expectations(self) -> None:
        script = _javascript(
            "http://127.0.0.1:1/pages/a.html",
            normal_targets()[0],
            Path("/tmp/a.png"),
            {"notes": {"1": "First."}},
        )
        self.assertIn(FOOTNOTE_CHECK, script)
        self.assertIn('{"notes": {"1": "First."}}', script)
        self.assertLess(script.index("page.screenshot"), script.index(FOOTNOTE_CHECK))

    def test_footnote_failures_are_reported_with_the_rest(self) -> None:
        self.assertEqual(_failures(PASSING), [])
        state = {**PASSING, "overflow": True, "footnotes": ["footnote 2: popover showed null"]}
        self.assertEqual(
            _failures(state),
            ["horizontal document overflow", "footnote 2: popover showed null"],
        )


class SetupWebKitTests(unittest.TestCase):
    def test_installs_when_listing_fails_on_a_fresh_cache(self) -> None:
        calls: list[list[str]] = []

        def run(arguments: list[str], **_: object) -> subprocess.CompletedProcess[str]:
            calls.append(arguments)
            if "--list" in arguments:
                return subprocess.CompletedProcess(
                    arguments, 1, "", "ENOENT: no such file or directory, scandir '.links'"
                )
            return subprocess.CompletedProcess(arguments, 0, "", "")

        with (
            patch("nnw_theme_tools.browser.shutil.which", return_value="/bin/playwright-cli"),
            patch("nnw_theme_tools.browser.subprocess.run", side_effect=run),
            patch("nnw_theme_tools.browser.sys.platform", "darwin"),
            redirect_stdout(io.StringIO()),
        ):
            setup_webkit()

        self.assertEqual(calls[-1], ["playwright-cli", "install-browser", "webkit"])


if __name__ == "__main__":
    unittest.main()
