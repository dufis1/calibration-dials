#!/usr/bin/env python3
"""Registry + pilot scaffolder for /calibrate-studio — the custom-dial lifecycle.

A custom dial moves author -> validate -> promote. This script owns the two
deterministic ends:

  create   write/overwrite a custom dial in the shared registry (status=unvalidated).
  list / show / remove   manage registry entries.
  scaffold-eval          materialize a judged-pilot dir (dialspec.json + pilot.md stub)
                         so eval/ can harden the dial with the same loop that
                         validated the built-in five.
  promote                after a passing pilot, flip status -> validated and record
                         the verdict.

The registry is the SHARED seam with the headline skill: it lives next to dials.py in
the sibling 'calibrate' skill, so studio.py writes exactly the file dials.py reads and
any custom dial renders in /calibrate automatically (tagged). Resolving it relative to
this script keeps that true in both deploy layouts — the ~/.claude/skills/ copy and the
bundled plugin — since both keep calibrate/ and calibrate-studio/ as sibling skill dirs.
Override with --registry for local testing.
"""
import argparse
import datetime
import json
import os
import re
import sys
from pathlib import Path

if sys.version_info < (3, 8):
    sys.exit("calibrate-studio: requires Python >= 3.8 (found "
             f"{sys.version_info[0]}.{sys.version_info[1]}). Point `python3` at a newer interpreter.")

HERE = Path(__file__).resolve().parent
DEFAULT_REGISTRY = HERE.parent / "calibrate" / "levers.user.json"
DEFAULT_PILOTS = HERE / "pilots"

CREATE_KEYS = ("dial", "slug", "axis", "judge_system", "order", "notches", "domains")


def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def load_registry(path):
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text() or "{}")
        return data if isinstance(data, dict) else {}
    except ValueError:
        return {}


def save_registry(path, reg):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(reg, indent=2, ensure_ascii=False) + "\n")


def find_dial(reg, key):
    """Match a registry entry by dial name or slug (case-insensitive)."""
    if key in reg:
        return key
    low = key.lower()
    for name, spec in reg.items():
        if name.lower() == low or spec.get("slug", "").lower() == low:
            return name
    return None


# ----- create --------------------------------------------------------------

def cmd_create(args):
    raw = sys.stdin.read() if args.spec in ("-", None) else Path(args.spec).read_text()
    try:
        spec = json.loads(raw)
    except ValueError as e:
        sys.exit(f"ERROR: --spec is not valid JSON ({e})")

    missing = [k for k in CREATE_KEYS if k not in spec]
    if missing:
        sys.exit(f"ERROR: spec missing required keys: {missing}")
    dial = spec["dial"].strip()
    order = spec["order"]
    notches = spec["notches"]
    if len(order) < 2:
        sys.exit("ERROR: a dial needs at least 2 notches")
    for label in order:
        nd = notches.get(label)
        if not nd or not nd.get("directive"):
            sys.exit(f"ERROR: notch '{label}' missing a directive")

    reg = load_registry(args.registry)
    # Guard against shadowing a built-in dial name.
    builtin = {"Detail", "Presentation", "Tone", "Rigor", "Autonomy"}
    if dial in builtin:
        sys.exit(f"ERROR: '{dial}' is a built-in dial name; choose another.")

    slug = spec.get("slug") or slugify(dial)
    entry = {
        "source": "user",
        "status": "unvalidated",
        "slug": slug,
        "order": order,
        "axis": spec["axis"],
        "judge_system": spec["judge_system"],
        "judge_noun": spec.get("judge_noun", dial),
        "notches": {lbl: {"directive": notches[lbl]["directive"],
                          "blurb": notches[lbl].get("blurb", "")} for lbl in order},
        "domains": spec["domains"],
        "eval": {"pilot_dir": str(args.pilots_dir / f"user-{slug}"),
                 "verdict": None, "validated_at": None},
    }
    existed = dial in reg
    reg[dial] = entry
    save_registry(args.registry, reg)
    print(f"{'updated' if existed else 'created'} custom dial '{dial}' "
          f"({len(order)} notches) -> {args.registry}")
    print(f"status: unvalidated  ·  it now renders in /calibrate (tagged custom · unvalidated)")
    print(f"next: harden it with  studio.py scaffold-eval {slug}")


# ----- list / show / remove ------------------------------------------------

def cmd_list(args):
    reg = load_registry(args.registry)
    if not reg:
        print("(no custom dials yet)")
        return
    for name, spec in reg.items():
        print(f"  {name:<18} {spec.get('status', '?'):<12} "
              f"notches: {', '.join(spec.get('order', []))}")


def cmd_show(args):
    reg = load_registry(args.registry)
    name = find_dial(reg, args.dial)
    if not name:
        sys.exit(f"ERROR: no custom dial matching '{args.dial}'")
    print(json.dumps(reg[name], indent=2, ensure_ascii=False))


def cmd_remove(args):
    reg = load_registry(args.registry)
    name = find_dial(reg, args.dial)
    if not name:
        sys.exit(f"ERROR: no custom dial matching '{args.dial}'")
    del reg[name]
    save_registry(args.registry, reg)
    print(f"removed '{name}' from the registry -> {args.registry}")
    print("(it no longer renders in /calibrate; its directive clears from CLAUDE.md on the next apply)")


# ----- scaffold-eval -------------------------------------------------------

PILOT_HEADER = """# {dial} — judged pilot battery

Fill in EACH item below: a realistic user prompt for the given domain, then one
exemplar per notch ({notches}) showing that notch's behavior on THAT prompt.

Keep the exemplars length-matched (build_exemplars.py audits the token ratio): the
judge must key on the dial's axis — {axis} — not on length. Bound the middle
notch(es) by contrast with their neighbors. See AUTHORING.md.
"""

ITEM_TMPL = """### #{i} — {domain} — {complexity}
**Prompt**
> TODO: a realistic user message in the {domain} domain that this dial should steer.

{notch_blocks}
"""

NOTCH_TMPL = """**{notch}**
> TODO: exemplar showing the "{notch}" end of the dial for the prompt above.
"""


def cmd_scaffold_eval(args):
    reg = load_registry(args.registry)
    name = find_dial(reg, args.dial)
    if not name:
        sys.exit(f"ERROR: no custom dial matching '{args.dial}'")
    spec = reg[name]
    pdir = Path(spec["eval"]["pilot_dir"])
    pdir.mkdir(parents=True, exist_ok=True)

    dialspec = {
        "dial": name,
        "slug": spec["slug"],
        "notches": spec["order"],
        "axis": spec["axis"],
        "judge_system": spec["judge_system"],
        "judge_noun": spec.get("judge_noun", name),
        "directives": {lbl: spec["notches"][lbl]["directive"] for lbl in spec["order"]},
        "blurbs": {lbl: spec["notches"][lbl].get("blurb", "") for lbl in spec["order"]},
        "domains": spec["domains"],
        "exemplar_version": "v1",
        "directive_version": "v1",
    }
    (pdir / "dialspec.json").write_text(json.dumps(dialspec, indent=2, ensure_ascii=False) + "\n")

    # Stub battery: per unique domain string, N items (Claude fills prompts+exemplars).
    domains = list(dict.fromkeys(spec["domains"].keys()))  # preserve order, dedupe
    per = args.items_per_domain
    complexities = ["simple", "medium", "hard", "medium"]
    notch_blocks = "\n".join(NOTCH_TMPL.format(notch=n) for n in spec["order"])
    items_md, i = [], 1
    for dom in domains:
        for k in range(per):
            items_md.append(ITEM_TMPL.format(i=i, domain=dom,
                                             complexity=complexities[k % len(complexities)],
                                             notch_blocks=notch_blocks))
            i += 1
    md = PILOT_HEADER.format(dial=name, notches="/".join(spec["order"]),
                             axis=spec["axis"]) + "\n" + "\n".join(items_md)
    (pdir / "pilot.md").write_text(md)

    print(f"scaffolded pilot for '{name}' -> {pdir}")
    print(f"  dialspec.json   ({len(spec['order'])} notches, domains: {', '.join(domains)})")
    print(f"  pilot.md        ({i-1} item stubs to fill in)")
    print("\nnext (run inside the eval harness, with the pilot dir as --dir):")
    print(f"  1. fill pilot.md exemplars, then:  python3 eval/build_exemplars.py --dir {pdir}")
    print(f"  2. GATE:                           python3 eval/judge_selftest.py --dir {pdir}")
    print(f"  3. sample+judge (costs quota):     python3 -u eval/run_pilot.py --dir {pdir} --n 5")
    print(f"  4. on overall PASS:                python3 studio.py promote {spec['slug']}")


# ----- promote -------------------------------------------------------------

def cmd_promote(args):
    reg = load_registry(args.registry)
    name = find_dial(reg, args.dial)
    if not name:
        sys.exit(f"ERROR: no custom dial matching '{args.dial}'")
    spec = reg[name]
    summary_file = args.verdict or os.path.join(spec["eval"]["pilot_dir"], "summary.json")
    if not os.path.exists(summary_file):
        sys.exit(f"ERROR: no verdict at {summary_file} — run eval/run_pilot.py first.")
    verdict = json.loads(Path(summary_file).read_text())
    if not verdict.get("overall_pass") and not args.force:
        sys.exit("ERROR: pilot did not pass (overall_pass=false). "
                 "Revise a directive (bump directive_version) and re-run, or use --force to "
                 "promote anyway (NOT recommended — it labels an unvalidated dial as validated).")
    spec["status"] = "validated"
    spec["eval"]["verdict"] = verdict
    spec["eval"]["validated_at"] = datetime.date.today().isoformat()
    save_registry(args.registry, reg)
    forced = "  (FORCED — verdict did not pass)" if args.force and not verdict.get("overall_pass") else ""
    print(f"promoted '{name}' -> validated{forced}")
    print(f"the 'unvalidated' tag drops from /calibrate on next open. verdict stored in the registry.")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY,
                    help="shared registry path (default: ~/.claude/skills/calibrate/levers.user.json)")
    ap.add_argument("--pilots-dir", type=Path, default=DEFAULT_PILOTS,
                    help="base dir for scaffolded pilots")
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("create"); c.add_argument("--spec", default="-",
                                                 help="JSON file with the dial spec, or '-' for stdin")
    sub.add_parser("list")
    sh = sub.add_parser("show"); sh.add_argument("dial")
    rm = sub.add_parser("remove"); rm.add_argument("dial")
    sc = sub.add_parser("scaffold-eval"); sc.add_argument("dial")
    sc.add_argument("--items-per-domain", type=int, default=4)
    pr = sub.add_parser("promote"); pr.add_argument("dial")
    pr.add_argument("--verdict", help="path to summary.json (default: the pilot dir's)")
    pr.add_argument("--force", action="store_true")

    args = ap.parse_args()
    {"create": cmd_create, "list": cmd_list, "show": cmd_show, "remove": cmd_remove,
     "scaffold-eval": cmd_scaffold_eval, "promote": cmd_promote}[args.cmd](args)


if __name__ == "__main__":
    main()
