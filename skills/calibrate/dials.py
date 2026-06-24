#!/usr/bin/env python3
"""Deterministic reader/writer for the /calibrate interaction-calibration output style.

Subcommands:
  read           Print the currently-applied dial->notch labels as JSON (for pre-seeding the widget).
  apply PAYLOAD  Regenerate the "Calibrated" output style + activate it from PAYLOAD.

PAYLOAD is the literal string the widget sends after "Calibrate: " — it lists ONLY the
dials the user set, e.g.  "Detail = Brief, Tone = Casual".  Full-state semantics: any
dial NOT listed (or explicitly marked default/none) is cleared -> its directive is
removed. An empty payload (or "reset ...") clears every dial, removes the style file, and
deactivates it.

The calibration lives in a Claude Code **output style** (https://code.claude.com/docs/en/output-styles):
  - the combined directives are written to a style file `output-styles/calibrated.md`
  - the style is activated by setting `outputStyle: "Calibrated"` in a settings file
Only the "Calibrated" style file and the `outputStyle` key are ever touched; the rest of
the settings file is preserved, and a user-set `outputStyle` other than ours is never clobbered.

Because an output style is part of the SYSTEM PROMPT (read once at session start), an apply
takes effect after `/clear` or a new session — `apply` prints that reminder.

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

# The output style we own. The name is what goes in the `outputStyle` setting and the
# style file's frontmatter; the filename is its lower-cased slug.
STYLE_NAME = "Calibrated"
STYLE_FILE = "calibrated.md"
STYLE_DESC = ("Interaction calibration set via /calibrate — steers detail, presentation, "
              "tone, rigor, and autonomy. Edit through /calibrate, not by hand.")
HEADER = "**Interaction calibration (set via /calibrate). Follow these directives:**"
CLEARED_WORDS = {"default", "unset", "none", ""}


def base_dir(args):
    """Root the calibration writes under: ~/.claude for --global, else the project's .claude/."""
    if args.global_:
        return Path.home() / ".claude"
    return Path(".claude")


def style_path(args):
    if args.style_file:
        return Path(args.style_file)
    return base_dir(args) / "output-styles" / STYLE_FILE


def settings_path(args):
    if args.settings_file:
        return Path(args.settings_file)
    # /config saves the picked output style to the LOCAL project settings; match that so
    # the two write paths agree. --global targets the user-level settings.
    return base_dir(args) / ("settings.json" if args.global_ else "settings.local.json")


def parse_labels(text):
    """Parse the machine-readable '<!-- dials: Detail=Brief; Tone=Casual -->' line from
    the style file body. Returns {} if absent."""
    if not text:
        return {}
    m = re.search(r"<!--\s*dials:\s*(.*?)\s*-->", text)
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


def load_settings(p):
    """Read a settings JSON file. Returns ({} , None) for a missing file; on invalid JSON
    returns (None, error) so callers can refuse to clobber the user's settings."""
    if not p.exists():
        return {}, None
    raw = p.read_text()
    if not raw.strip():
        return {}, None
    try:
        data = json.loads(raw)
    except ValueError as e:
        return None, f"{p} is not valid JSON ({e})"
    if not isinstance(data, dict):
        return None, f"{p} is not a JSON object"
    return data, None


def write_settings(p, data):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2) + "\n")


def build_style(selected):
    pairs = [f"{d}={selected[d]}" for d in LEVERS if d in selected]
    lines = [
        "---",
        f"name: {STYLE_NAME}",
        f"description: {STYLE_DESC}",
        "keep-coding-instructions: true",
        "---",
        "<!-- dials: " + "; ".join(pairs) + " -->",
        "<!-- Managed by /calibrate. Do not hand-edit; rerun /calibrate to change. -->",
        "",
        HEADER,
        "",
    ]
    for d in LEVERS:
        if d in selected:
            lines.append(f"- {d} = {selected[d]}: {LEVERS[d][selected[d]]}")
    return "\n".join(lines) + "\n"


def cmd_read(args):
    """Pre-seed for the widget: the applied dial->notch labels, but ONLY when our style is
    the active one (a user who switched away via /config should see a blank widget)."""
    sp = style_path(args)
    settings, err = load_settings(settings_path(args))
    active = settings is not None and settings.get("outputStyle") == STYLE_NAME
    labels = parse_labels(sp.read_text()) if (active and sp.exists()) else {}
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
    sp = style_path(args)
    setp = settings_path(args)

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

    # Refuse to touch settings we can't parse rather than clobber the user's file.
    settings, serr = load_settings(setp)
    if serr:
        print("ERROR (nothing written): " + serr)
        sys.exit(1)

    cleared = [d for d in LEVERS if d not in selected]  # full-state: unlisted = default

    if selected:
        sp.parent.mkdir(parents=True, exist_ok=True)
        sp.write_text(build_style(selected))
        if settings.get("outputStyle") != STYLE_NAME:
            settings["outputStyle"] = STYLE_NAME
            write_settings(setp, settings)
        activated = True
    else:
        # Full reset: remove our style file and deactivate — but only if WE are the active
        # style (never strip a style the user picked separately).
        if sp.exists():
            sp.unlink()
        if settings.get("outputStyle") == STYLE_NAME:
            del settings["outputStyle"]
            write_settings(setp, settings)
        activated = False

    set_desc = ", ".join(f"{d}={selected[d]}" for d in LEVERS if d in selected) or "(none)"
    if activated:
        print(f"Wrote output style: {sp.resolve()}")
        print(f"Activated outputStyle=\"{STYLE_NAME}\" in {setp.resolve()}")
    else:
        print(f"Reset: removed the {STYLE_NAME} output style and deactivated it.")
    print(f"Set: {set_desc}")
    print(f"Cleared (now Claude default): {', '.join(cleared) if cleared else '(none)'}")
    print("Takes effect after /clear or a new session (output style = system prompt).")


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
    ap.add_argument("--global", dest="global_", action="store_true",
                    help="target the user level (~/.claude/output-styles + ~/.claude/settings.json)")
    ap.add_argument("--style-file", help="explicit output-style file path (testing override)")
    ap.add_argument("--settings-file", help="explicit settings.json path (testing override)")
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
