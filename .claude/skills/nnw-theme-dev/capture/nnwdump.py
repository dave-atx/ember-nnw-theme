"""
nnwdump — capture a NetNewsWire article-substitution dictionary as a TOML fixture.

This is an lldb command. It reads the local `[String: String]` substitutions
dictionary that ArticleRenderer builds for the article currently being rendered,
and writes it to disk as a clean TOML fixture you can replay with render.py.

It replaces the old manual routine of pasting a hand-escaping expr into lldb and
copying the result out of the console. Values cross the lldb boundary base64-
encoded (so nothing needs escaping and nothing gets truncated), and the TOML is
formatted on the Python side using literal strings — `'''…'''` for HTML/multiline
values (zero escaping), `'…'` for plain values — so the file stays readable and
diff-friendly.

--------------------------------------------------------------------------------
Setup (once): in NetNewsWire's ArticleRenderer.swift, put a breakpoint on the
`return d` line at the end of articleSubstitutions() (so the dictionary `d` is
fully populated and in scope). Then, from the Xcode/lldb console, import with an
ABSOLUTE path (lldb's working directory under Xcode is `/`, so a relative import
path fails):

    (lldb) command script import /abs/path/to/.claude/skills/nnw-theme-dev/capture/nnwdump.py

(Or add that line to ~/.lldbinit to load it automatically every session.)

Usage, stopped at the breakpoint:

    (lldb) nnwdump test/my-case.toml    # relative -> resolved against the repo root
    (lldb) nnwdump                      # defaults to <repo>/test/nnw-capture.toml
    (lldb) nnwdump /abs/path/case.toml  # absolute path honored as-is

A relative OUTPUT path is resolved against the repo root inferred from this
script's location (NOT lldb's `/` working directory), so `test/my-case.toml`
lands in the repo. Select the article in NetNewsWire, let it hit the breakpoint,
run nnwdump, then continue. The written .toml is ready for render.py.

The variable name defaults to `d`; override with --var if you stop somewhere the
dictionary has a different name:

    (lldb) nnwdump --var d ~/src/nnw-theme/test/my-case.toml
"""

import base64
import shlex
import optparse
import os

import lldb


# Keys that should stay literal/last for readability in the emitted TOML.
_HTML_KEYS = {"body"}


def _repo_root():
    """Best-effort repo root, inferred from this script's install location:
    <repo>/.claude/skills/nnw-theme-dev/capture/nnwdump.py -> parents[4].
    Falls back to the home directory if the layout is unexpected.
    """
    try:
        return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
    except Exception:  # pragma: no cover - defensive
        return os.path.expanduser("~")


def _resolve_out_path(arg):
    """Resolve the output path.

    lldb's working directory (under Xcode) is `/`, so a relative path would
    resolve to a read-only location like `/test/…`. Absolute and `~` paths are
    honored as given; a relative path is resolved against the repo root inferred
    from this script's location, which is almost always what the user means.
    """
    arg = os.path.expanduser(arg)
    if os.path.isabs(arg):
        return os.path.abspath(arg)
    return os.path.abspath(os.path.join(_repo_root(), arg))


def _make_parser():
    parser = optparse.OptionParser(prog="nnwdump", usage="nnwdump [--var NAME] [OUTPUT.toml]")
    parser.add_option("--var", dest="var", default="d",
                      help="name of the [String:String] dictionary in scope (default: d)")
    parser.add_option("--article", dest="article", default="article",
                      help="name of the Article value in scope, used to embed the real "
                           "feed icon as a data: URL (default: article)")
    parser.add_option("--no-icon", dest="no_icon", action="store_true", default=False,
                      help="do not resolve the feed icon; keep the nnwImageIcon: avatar_src")
    return parser


def _toml_basic(value):
    """Escape a value for a TOML basic (double-quoted) string."""
    out = value.replace("\\", "\\\\").replace('"', '\\"')
    out = out.replace("\n", "\\n").replace("\t", "\\t").replace("\r", "\\r")
    # Remaining control chars -> \uXXXX
    return "".join(c if ord(c) >= 0x20 else "\\u%04x" % ord(c) for c in out)


def _emit(key, value):
    """Render one `key = value` TOML line, choosing the friendliest string form."""
    is_html = ("\n" in value) or ("<" in value)
    if is_html and "'''" not in value:
        # Multiline literal. TOML trims a single newline immediately after the
        # opening delimiter, so the leading "\n" we add is not part of the value.
        return "%s = '''\n%s'''" % (key, value)
    if ("\n" not in value) and ("'" not in value):
        return "%s = '%s'" % (key, value)
    return '%s = "%s"' % (key, _toml_basic(value))


def _sort_key(item):
    key = item[0]
    # HTML/body keys sort to the very end so the readable header stays on top.
    return (1 if key in _HTML_KEYS else 0, key)


def _eval_blob(ci, inner_expr):
    """Evaluate a Swift String expression and return its exact text, or None.

    The inner expression is wrapped so Swift hands us a single base64 token:
    `Data((<inner>).utf8).base64EncodedString()`. That token survives however
    lldb formats a String (quotes, escaping, truncation-avoidance) because we
    strip surrounding quotes/whitespace and base64-decode the rest. Returns the
    decoded UTF-8 text, or None if the eval failed.
    """
    wrapped = 'Data((%s).utf8).base64EncodedString()' % inner_expr
    ret = lldb.SBCommandReturnObject()
    ci.HandleCommand('expression -l Swift -O -- ' + wrapped, ret)
    if not ret.Succeeded():
        return None, (ret.GetError() or "").strip()
    token = (ret.GetOutput() or "").strip().strip('"').strip()
    if not token:
        return "", None
    try:
        return base64.b64decode(token).decode("utf-8"), None
    except Exception as exc:  # pragma: no cover - defensive
        return None, "could not base64-decode debugger output: %s" % exc


def _resolve_icon_data_url(ci, article_var):
    """Return a data: URL for the article's feed icon, or None.

    Mirrors ArticleIconSchemeHandler: iconImage().image -> PNG via the app's
    cross-platform dataRepresentation(). `?? ""` keeps the result a non-optional
    String so lldb never prints `Optional(...)`; an empty result means no icon.
    """
    inner = ('%s.iconImage()?.image.dataRepresentation()?.base64EncodedString() ?? ""'
             % article_var)
    b64, _err = _eval_blob(ci, inner)
    if not b64:
        return None
    return "data:image/png;base64," + b64


def nnwdump(debugger, command, result, internal_dict):
    parser = _make_parser()
    try:
        opts, args = parser.parse_args(shlex.split(command))
    except SystemExit:
        result.SetError("could not parse arguments; usage: nnwdump [--var NAME] [OUTPUT.toml]")
        return

    out_path = _resolve_out_path(args[0] if args else "test/nnw-capture.toml")
    varname = opts.var

    frame = (debugger.GetSelectedTarget()
             .GetProcess().GetSelectedThread().GetSelectedFrame())
    if not frame or not frame.IsValid():
        result.SetError("no valid stack frame; are you stopped at a breakpoint?")
        return

    # Avoid truncation of the (possibly large) base64 string summary.
    debugger.HandleCommand("settings set target.max-string-summary-length 0")

    # Inner string is "key\tbase64(value)" lines; base64 has no tabs/newlines and
    # keys are simple identifiers, so the decoded stream splits unambiguously.
    inner = ('%s.map { $0.key + "\\t" + Data($0.value.utf8).base64EncodedString() }'
             '.joined(separator: "\\n")' % varname)

    ci = debugger.GetCommandInterpreter()
    raw, err = _eval_blob(ci, inner)
    if raw is None:
        result.SetError("failed to evaluate `%s`: %s\n"
                        "Are you stopped where the substitutions dict is in scope?"
                        % (varname, err or "unknown error"))
        return
    raw = raw.strip()
    if not raw:
        result.SetError("`%s` produced no output; is it an empty or wrong variable?" % varname)
        return

    pairs = []
    for line in raw.split("\n"):
        line = line.strip()
        if not line or "\t" not in line:
            continue
        key, b64 = line.split("\t", 1)
        try:
            value = base64.b64decode(b64).decode("utf-8")
        except Exception as exc:  # pragma: no cover - defensive
            result.SetError("could not decode value for '%s': %s" % (key, exc))
            return
        pairs.append((key.strip(), value))

    if not pairs:
        result.SetError("parsed zero key/value pairs from the debugger output.")
        return

    # Replace the app-internal `nnwImageIcon:` avatar with the actual feed icon
    # as a data: URL, so previews show the real icon instead of a placeholder.
    icon_note = ""
    if not opts.no_icon:
        data_url = _resolve_icon_data_url(ci, opts.article)
        if data_url:
            pairs = [(k, data_url if k == "avatar_src" else v) for k, v in pairs]
            if not any(k == "avatar_src" for k, _ in pairs):
                pairs.append(("avatar_src", data_url))
            icon_note = " (embedded real feed icon)"
        else:
            icon_note = " (no feed icon; kept nnwImageIcon: placeholder)"

    pairs.sort(key=_sort_key)
    header = ("# NetNewsWire article fixture captured with nnwdump.\n"
              "# Replay with: python3 render.py %s\n\n" % os.path.basename(out_path))
    body = "\n".join(_emit(k, v) for k, v in pairs) + "\n"

    try:
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(header + body)
    except OSError as exc:
        result.SetError("could not write %s: %s" % (out_path, exc))
        return

    result.AppendMessage("nnwdump: wrote %d keys to %s%s" % (len(pairs), out_path, icon_note))


def __lldb_init_module(debugger, internal_dict):
    debugger.HandleCommand("command script add -f nnwdump.nnwdump nnwdump")
    print('nnwdump: registered. Usage at a breakpoint: nnwdump [--var NAME] [OUTPUT.toml]')
