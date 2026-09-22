from __future__ import annotations

import tomllib
import unittest

from nnw_theme_tools.project import ThemeError, footnote_expectations


def _expectations(text: str) -> dict:
    return footnote_expectations(tomllib.loads(text), "fixtures/f.toml")


class FootnoteExpectationTests(unittest.TestCase):
    def test_fixture_without_expectations_expects_nothing(self) -> None:
        self.assertEqual(_expectations('title = "T"'), {})

    def test_notes_keep_their_order_and_plain_links_are_selectors(self) -> None:
        expected = _expectations(
            'body = "<p>x</p>"\n'
            "[expect.footnotes]\n"
            'plain_links = ["#ordinary"]\n'
            "keep_with_word = true\n"
            "[expect.footnotes.notes]\n"
            '"2" = "Second."\n'
            '"1" = "First."\n'
        )
        self.assertEqual(list(expected["notes"].items()), [("2", "Second."), ("1", "First.")])
        self.assertEqual(expected["plain_links"], ["#ordinary"])
        self.assertIs(expected["keep_with_word"], True)

    def test_typos_and_wrong_types_are_errors(self) -> None:
        for text, message in (
            ("[expect.footnote]\nnotes = {}", r"only a \[expect.footnotes\]"),
            ("expect = 1", r"only a \[expect.footnotes\]"),
            ("[expect.footnotes]\nnote = {}", "unknown .*note"),
            ('[expect.footnotes]\nnotes = {"1" = 1}', "map markers to text"),
            ('[expect.footnotes]\nplain_links = "#a"', "CSS selectors"),
            ('[expect.footnotes]\nkeep_with_word = "yes"', "true or false"),
        ):
            with self.subTest(text=text), self.assertRaisesRegex(ThemeError, message):
                _expectations(text)


if __name__ == "__main__":
    unittest.main()
