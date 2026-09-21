"""nnwdump: capture a NetNewsWire article as a fixture, from inside lldb.

Stopped at the final `return d` of ArticleRenderer.articleSubstitutions(), this
reads the substitution dictionary NetNewsWire built for the selected article and
writes it as a TOML fixture. `uv run nnw-theme capture` prints the setup steps.

Values cross the debugger boundary base64-encoded, so nothing is truncated or
mis-escaped. HTML values are written as '''literal''' strings, so fixtures stay
readable and diff cleanly.

This file runs in Xcode's lldb Python, not the project's: keep it standard-library
only and compatible with Python 3.9. It imports lldb lazily so the formatting
helpers can be tested without a debugger.
"""

from __future__ import annotations

import base64
import optparse
import shlex
from pathlib import Path

USAGE = "nnwdump [--var NAME] [--article NAME] [--no-icon] [OUTPUT.toml]"
DEFAULT_OUTPUT = "fixtures/nnw-capture.toml"
# Sorted last so the short metadata stays at the top of the file.
_HTML_KEYS = {"body"}


def repository_root() -> Path:
    """<root>/src/nnw_theme_tools/nnwdump.py -> <root>."""
    return Path(__file__).resolve().parents[2]


def resolve_output(argument: str) -> Path:
    """lldb's working directory under Xcode is /, so resolve against the repository."""
    path = Path(argument).expanduser()
    return path if path.is_absolute() else repository_root() / path


def _toml_basic(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    escaped = escaped.replace("\n", "\\n").replace("\t", "\\t").replace("\r", "\\r")
    return "".join(c if ord(c) >= 0x20 and c != "\x7f" else f"\\u{ord(c):04x}" for c in escaped)


def toml_line(key: str, value: str) -> str:
    """One `key = value` line in the most readable string form that is exact."""
    # Literal strings cannot hold control characters (multiline ones allow newlines).
    literal = not any((ord(c) < 0x20 and c not in "\t\n") or c == "\x7f" for c in value)
    if literal and ("\n" in value or "<" in value) and "'''" not in value:
        # TOML drops the newline right after the opening delimiter, so this one is
        # layout, and a value's own leading newline survives.
        return f"{key} = '''\n{value}'''"
    if literal and "\n" not in value and "'" not in value:
        return f"{key} = '{value}'"
    return f'{key} = "{_toml_basic(value)}"'


def fixture_text(pairs: list[tuple[str, str]], name: str) -> str:
    ordered = sorted(pairs, key=lambda pair: (pair[0] in _HTML_KEYS, pair[0]))
    header = (
        "# NetNewsWire article captured with nnwdump.\n"
        f"# Preview with: uv run nnw-theme render {name}\n\n"
    )
    return header + "\n".join(toml_line(key, value) for key, value in ordered) + "\n"


def _evaluate(interpreter, expression: str):
    """The exact text of a Swift String expression, or (None, error)."""
    import lldb

    wrapped = f"Data(({expression}).utf8).base64EncodedString()"
    result = lldb.SBCommandReturnObject()
    interpreter.HandleCommand("expression -l Swift -O -- " + wrapped, result)
    if not result.Succeeded():
        return None, (result.GetError() or "").strip()
    token = (result.GetOutput() or "").strip().strip('"').strip()
    try:
        return base64.b64decode(token).decode("utf-8"), None
    except ValueError as error:
        return None, f"could not decode debugger output: {error}"


def _icon_data_url(interpreter, article: str):
    # Mirrors ArticleIconSchemeHandler: the feed icon as PNG data.
    encoded, _ = _evaluate(
        interpreter,
        f'{article}.iconImage()?.image.dataRepresentation()?.base64EncodedString() ?? ""',
    )
    return f"data:image/png;base64,{encoded}" if encoded else None


def nnwdump(debugger, command, result, internal_dict):
    parser = optparse.OptionParser(prog="nnwdump", usage=USAGE)
    parser.add_option("--var", default="d", help="substitution dictionary (default: d)")
    parser.add_option("--article", default="article", help="Article value (default: article)")
    parser.add_option("--no-icon", action="store_true", help="keep the generated feed icon")
    try:
        options, arguments = parser.parse_args(shlex.split(command))
    except SystemExit:
        result.SetError(f"usage: {USAGE}")
        return
    output = resolve_output(arguments[0] if arguments else DEFAULT_OUTPUT)

    frame = debugger.GetSelectedTarget().GetProcess().GetSelectedThread().GetSelectedFrame()
    if not frame or not frame.IsValid():
        result.SetError("no stack frame; stop at the breakpoint first")
        return
    debugger.HandleCommand("settings set target.max-string-summary-length 0")

    # One "key<TAB>base64(value)" line per entry; base64 never contains either separator.
    interpreter = debugger.GetCommandInterpreter()
    raw, error = _evaluate(
        interpreter,
        f'{options.var}.map {{ $0.key + "\\t" + Data($0.value.utf8).base64EncodedString() }}'
        '.joined(separator: "\\n")',
    )
    if raw is None:
        result.SetError(f"could not read `{options.var}`: {error}. Stop at `return d` first.")
        return
    pairs = []
    for line in raw.strip().splitlines():
        key, _, encoded = line.partition("\t")
        if key and encoded:
            pairs.append((key.strip(), base64.b64decode(encoded).decode("utf-8")))
    if not pairs:
        result.SetError(f"`{options.var}` is empty; is this the substitution dictionary?")
        return

    note = ""
    if not options.no_icon:
        icon = _icon_data_url(interpreter, options.article)
        if icon:
            pairs = [(key, value) for key, value in pairs if key != "avatar_src"]
            pairs.append(("avatar_src", icon))
            note = " with the feed's icon"
        else:
            note = "; the feed has no icon, so previews generate one"

    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(fixture_text(pairs, output.stem), encoding="utf-8")
    except OSError as error:
        result.SetError(f"could not write {output}: {error}")
        return
    result.AppendMessage(f"nnwdump: wrote {len(pairs)} values to {output}{note}")


def __lldb_init_module(debugger, internal_dict):
    debugger.HandleCommand("command script add -f nnwdump.nnwdump nnwdump")
    print(f"nnwdump is ready. At the breakpoint: {USAGE}")
