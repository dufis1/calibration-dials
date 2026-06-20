#!/usr/bin/env python3
"""Deterministic reader/writer for the /calibrate interaction-calibration block.

Subcommands:
  read           Print the currently-applied dial->notch labels as JSON (for pre-seeding the widget).
  apply PAYLOAD  Rewrite ONLY the <!-- dial-settings --> block from PAYLOAD.

PAYLOAD is the literal string the widget sends after "Calibrate: " — it lists ONLY the
dials the user set, e.g.  "Detail = Brief, Tone = Casual".  Full-state semantics: any
dial NOT listed (or explicitly marked default/none) is cleared -> its directive is
removed. An empty payload (or "reset ...") clears every dial and removes the block.

Only the text between the start/end markers is ever touched; the rest of CLAUDE.md is left exactly as-is.
Directives come from levers.json next to this script (the validated built-in dials), plus
levers.user.json if present (custom dials authored via /calibrate-studio).

Subcommand `userdials` prints the custom dials (labels + hover blurbs + status) as JSON so
the widget can render them alongside the built-in five.
"""
import sys
import os
import json
import re
import argparse
from pathlib import Path

if sys.version_info < (3, 8):
    sys.exit("calibrate: requires Python >= 3.8 (found "
             f"{sys.version_info[0]}.{sys.version_info[1]}). Point `python3` at a newer interpreter.")

HERE = Path(__file__).resolve().parent
BUILTIN = json.loads((HERE / "levers.json").read_text())
USER_PATH = HERE / "levers.user.json"


def load_user():
    """Custom dials authored via /calibrate-studio. Registry shape:
      {Dial: {source, status, order:[...], axis, notches:{Label:{directive, blurb}}, eval:{...}}}
    Returns {} when the registry is absent or unreadable, so a missing/empty file
    means the headline /calibrate behaves exactly as it did before this feature."""
    if not USER_PATH.exists():
        return {}
    try:
        data = json.loads(USER_PATH.read_text() or "{}")
        return data if isinstance(data, dict) else {}
    except ValueError:
        return {}


USER = load_user()
# Flatten everything into the same {Dial: {Notch: directive}} shape the rest of the
# script already speaks. Built-in dials first, then user dials (deterministic block
# order); a user dial may NOT shadow a built-in one.
LEVERS = dict(BUILTIN)
for _dial, _spec in USER.items():
    if _dial in BUILTIN:
        continue
    _notches = _spec.get("notches", {})
    LEVERS[_dial] = {lbl: nd.get("directive", "") for lbl, nd in _notches.items()}

START = "<!-- dial-settings:start -->"
END = "<!-- dial-settings:end -->"
HEADER = "**Interaction calibration (set via /calibrate). Follow these directives in this project:**"
CLEARED_WORDS = {"default", "unset", "none", ""}


def target_path(args):
    if args.file:
        return Path(args.file)
    if args.global_:
        return Path.home() / ".claude" / "CLAUDE.md"
    return Path("CLAUDE.md")


def extract_block(text):
    if START in text and END in text:
        return text.split(START, 1)[1].split(END, 1)[0]
    return None


def parse_labels(block):
    """Parse the machine-readable '<!-- dials: Detail=Brief; Tone=Casual -->' line."""
    if not block:
        return {}
    m = re.search(r"<!--\s*dials:\s*(.*?)\s*-->", block)
    if not m:
        return {}
    out = {}
    for part in m.group(1).split(";"):
        part = part.strip()
        if "=" in part:
            k, v = part.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def parse_payload(s):
    out = {}
    for part in s.split(","):
        if "=" in part:
            k, v = part.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def build_block(selected):
    pairs = [f"{d}={selected[d]}" for d in LEVERS if d in selected]
    lines = [START, "<!-- dials: " + "; ".join(pairs) + " -->", HEADER]
    for d in LEVERS:
        if d in selected:
            lines.append(f"- {d} = {selected[d]}: {LEVERS[d][selected[d]]}")
    lines.append(END)
    return "\n".join(lines)


def cmd_read(args):
    p = target_path(args)
    labels = parse_labels(extract_block(p.read_text())) if p.exists() else {}
    valid = {d: n for d, n in labels.items() if d in LEVERS and n in LEVERS[d]}
    print(json.dumps(valid))


def cmd_userdials(args):
    """Emit custom dials for the widget: name, status, and [label, blurb] stops in
    notch order. Built-in five are hardcoded in the widget; this is only the extras."""
    out = []
    for dial, spec in USER.items():
        if dial in BUILTIN:
            continue
        notches = spec.get("notches", {})
        order = spec.get("order") or list(notches.keys())
        stops = [[lbl, notches.get(lbl, {}).get("blurb", "")] for lbl in order if lbl in notches]
        out.append({"name": dial, "status": spec.get("status", "unvalidated"), "stops": stops})
    print(json.dumps(out))


def cmd_apply(args):
    p = target_path(args)
    selected, errors = {}, []
    for d, v in parse_payload(args.payload).items():
        if d not in LEVERS:
            errors.append(f"unknown dial '{d}'")
        elif v.lower() in CLEARED_WORDS:
            continue  # explicit clear
        elif v not in LEVERS[d]:
            errors.append(f"unknown notch for {d}: '{v}'")
        else:
            selected[d] = v
    if errors:
        print("ERROR (nothing written): " + "; ".join(errors))
        sys.exit(1)
    cleared = [d for d in LEVERS if d not in selected]  # full-state: unlisted = default

    block = build_block(selected) if selected else ""
    text = p.read_text() if p.exists() else ""
    if START in text and END in text:
        pre = text.split(START, 1)[0].rstrip("\n")
        post = text.split(END, 1)[1].lstrip("\n")
        parts = [s for s in (pre, block, post) if s]
        new = ("\n\n".join(parts) + "\n") if parts else ""
    elif block:
        base = text.rstrip("\n")
        new = (base + "\n\n" if base else "") + block + "\n"
    else:
        new = text  # nothing set and no existing block: no-op

    if new != text:
        p.write_text(new)

    set_desc = ", ".join(f"{d}={selected[d]}" for d in LEVERS if d in selected) or "(none)"
    print(f"Wrote {p.resolve()}")
    print(f"Set: {set_desc}")
    print(f"Cleared (now Claude default): {', '.join(cleared) if cleared else '(none)'}")


# Entrypoints known to render the interactive HTML widget. Everything else has no widget
# surface and would just print the widget's raw HTML, so we route it to the AskUserQuestion
# picker fallback (see SKILL.md). The picker works on every surface, so an unknown/empty
# entrypoint safely defaults to it.
#   Confirmed CLAUDE_CODE_ENTRYPOINT values: "claude-desktop" = desktop app (widget),
#   "cli" = terminal Claude Code (picker). Add other widget-capable entrypoints here.
WIDGET_ENTRYPOINTS = {"claude-desktop"}


def cmd_surface(args):
    """Print 'widget' if this surface can render the HTML dial widget, else 'picker'.
    Detection is by CLAUDE_CODE_ENTRYPOINT; the skill branches on this before rendering."""
    ep = os.environ.get("CLAUDE_CODE_ENTRYPOINT", "")
    print("widget" if ep in WIDGET_ENTRYPOINTS else "picker")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--global", dest="global_", action="store_true", help="target ~/.claude/CLAUDE.md")
    ap.add_argument("--file", help="explicit target path (overrides --global)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("read")
    sub.add_parser("userdials")
    sub.add_parser("surface")
    a = sub.add_parser("apply")
    a.add_argument("payload")
    args = ap.parse_args()
    {"read": cmd_read, "userdials": cmd_userdials, "surface": cmd_surface, "apply": cmd_apply}[args.cmd](args)


if __name__ == "__main__":
    main()
