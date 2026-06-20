"""Parse the frozen exemplars from <dir>/pilot.md and freeze them to
<dir>/exemplars.json, running the LENGTH-MATCH AUDIT (the posture-vs-verbosity
confound control): for each item, report the token spread across the notch
exemplars and flag any item whose max/min ratio exceeds LENGTH_RATIO_FLAG. If the
exemplars differ wildly in length, the judge can learn "longer = higher notch"
instead of scoring the intended axis — so rebalance flagged items before trusting
any downstream number.

Generalized from pilot/rigor/build_exemplars.py: the notch labels come from
dialspec.json, so the same parser works for any custom dial.

pilot.md format (per item):
    ### #1 — <Domain> — <complexity>
    **Prompt**
    > the user message ...
    **<Notch1>**
    > exemplar text ...
    **<Notch2>**
    > ...

Run: python3 build_exemplars.py --dir <pilot_dir>
"""
import argparse
import json
import os
import re
import sys

from harness import (load_spec, count_tokens, tokenizer_name,
                     LENGTH_RATIO_FLAG, JUDGE_MODEL)

ITEM_RE = re.compile(r'^###\s+#(\d+)\s+—\s+(.+?)\s+—\s+(.+?)\s*$', re.M)
PROMPT_RE = re.compile(r'^\*\*Prompt\*\*\s*$', re.M)


def dequote(block):
    out = []
    for line in block.splitlines():
        if line.startswith(">"):
            rest = line[1:]
            out.append(rest[1:] if rest.startswith(" ") else rest)
    return " ".join(p.strip() for p in out if p.strip()).strip()


def extract_blocks(section, notch_re):
    prompt = ""
    pm = PROMPT_RE.search(section)
    first_notch = notch_re.search(section)
    if pm:
        end = first_notch.start() if first_notch else len(section)
        prompt = dequote(section[pm.end():end])
    exemplars = {}
    nm = list(notch_re.finditer(section))
    for j, m in enumerate(nm):
        start = m.end()
        end = nm[j + 1].start() if j + 1 < len(nm) else len(section)
        exemplars[m.group(1)] = dequote(section[start:end])
    return prompt, exemplars


def parse(md, notch_re):
    items = {}
    ms = list(ITEM_RE.finditer(md))
    for i, m in enumerate(ms):
        start = m.end()
        end = ms[i + 1].start() if i + 1 < len(ms) else len(md)
        prompt, exemplars = extract_blocks(md[start:end], notch_re)
        items[int(m.group(1))] = {
            "prompt": prompt,
            "domain": m.group(2).strip(),
            "complexity": m.group(3).strip(),
            "exemplars": exemplars,
        }
    return items


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=".")
    args = ap.parse_args()

    spec = load_spec(args.dir)
    notches = spec["notches"]
    notch_re = re.compile(r'^\*\*(' + "|".join(re.escape(n) for n in notches) + r')\*\*\s*$', re.M)

    pilot_md = os.path.join(args.dir, "pilot.md")
    out = os.path.join(args.dir, "exemplars.json")
    with open(pilot_md, encoding="utf-8") as f:
        md = f.read()
    items = parse(md, notch_re)

    out_items = {}
    violations = []
    flags = []
    for item_id in sorted(items):
        item = items[item_id]
        ex = item["exemplars"]
        missing = [n for n in notches if n not in ex or not ex[n]]
        if missing:
            violations.append(f"#{item_id}: missing/empty notches {missing}")
            continue
        if not item["prompt"]:
            violations.append(f"#{item_id}: empty prompt")
            continue
        toks = {n: count_tokens(ex[n]) for n in notches}
        ratio = max(toks.values()) / max(1, min(toks.values()))
        if ratio > LENGTH_RATIO_FLAG:
            flags.append(f"#{item_id}: length ratio {ratio:.2f} > {LENGTH_RATIO_FLAG} "
                         f"(tokens { {n: toks[n] for n in notches} })")
        out_items[str(item_id)] = {
            "prompt": item["prompt"],
            "domain": item["domain"],
            "complexity": item["complexity"],
            "exemplars": {n: ex[n] for n in notches},
            "exemplar_tokens": toks,
        }

    table = {
        "dial": spec["dial"],
        "notches": notches,
        "exemplar_version": spec.get("exemplar_version", "v1"),
        "judge_model": JUDGE_MODEL,
        "tokenizer": tokenizer_name(),
        "length_ratio_flag": LENGTH_RATIO_FLAG,
        "items": out_items,
    }

    print(f"tokenizer: {tokenizer_name()}")
    print(f"parsed {len(out_items)} items\n")
    head = "/".join(n[:3] for n in notches)
    print(f"{'item':>4}  {'domain':<14}  tokens ({head})      ratio")
    for item_id in sorted(items):
        k = str(item_id)
        if k not in out_items:
            continue
        t = out_items[k]["exemplar_tokens"]
        toks = "/".join(f"{t[n]:>3}" for n in notches)
        ratio = max(t.values()) / max(1, min(t.values()))
        mark = " <-- FLAG" if ratio > LENGTH_RATIO_FLAG else ""
        print(f"{item_id:>4}  {out_items[k]['domain']:<14}  {toks:<24}  {ratio:.2f}{mark}")

    print()
    if violations:
        print("STRUCTURE VIOLATIONS (not frozen):")
        for v in violations:
            print("  -", v)
        sys.exit(1)

    with open(out, "w", encoding="utf-8") as f:
        json.dump(table, f, indent=2, ensure_ascii=False)
    print(f"froze {len(out_items)} items -> {out}")
    if flags:
        print("\nLENGTH-MATCH FLAGS (rebalance these before trusting the judge):")
        for fl in flags:
            print("  -", fl)
    else:
        print("length-match: OK (all items within ratio cap)")


if __name__ == "__main__":
    main()
