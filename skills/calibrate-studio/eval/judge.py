"""Config-driven Opus comparative-bracketing judge (generalized from the Rigor
pilot's judge.py). Given the item prompt, a reply, and the frozen per-notch
exemplars, it places the reply on a continuous 1.0-N.0 scale by bracketing it
between the two exemplars it most resembles. The discrete notch is DERIVED by
rounding — one judgment, read two ways.

The scale name, the notches, and the confound-control system line all come from
`dialspec.json` (so the judge keys on the dial's *intended* axis and is told to
ignore everything else). The exemplars are length-matched at build time so the
judge can't learn "longer = higher notch".

    judge(dir, item_id, reply, table=None, model=...) -> {position, notch, rationale}

CLI smoke test:  python3 judge.py --dir <pilot_dir>
"""
import argparse
import json
import os

from harness import (load_spec, call_claude, extract_json, JUDGE_VERSION,
                     JUDGE_MODEL)

JUDGE_TEMPLATE = """A user sent the following message:

<user_message>
{prompt}
</user_message>

Below are {n} REFERENCE responses to that exact message, each illustrating a fixed
point on a 1-{n} "{noun}" scale — {axis}:

{exemplar_block}

Now score this RESPONSE:

<response>
{reply}
</response>

Place the response on the 1.0-{n}.0 scale by deciding which two reference points it
falls between and how close it is to each (squarely at a reference = that integer;
halfway between two adjacent references = the .5 between them).

CRITICAL SCORING RULES:
- Score ONLY the dimension this scale measures: {axis}. The reference points define it.
- IGNORE everything else — length, tone, politeness, formatting, writing quality —
  EXCEPT where those properties literally ARE the dimension being scored.
- Judge against the reference points only — they define the scale.

Respond with ONLY a JSON object, no other text:
{{"position": <number 1.0-{n}.0>, "rationale": "<one short sentence>"}}"""


def _table_path(d):
    return os.path.join(d, "exemplars.json")


def load_table(d):
    with open(_table_path(d), encoding="utf-8") as f:
        return json.load(f)


def _exemplar_block(item, notches):
    ex = item["exemplars"]
    lines = []
    for i, n in enumerate(notches, start=1):
        lines.append(f"[Reference {i} = {n} (position {i})]\n{ex[n]}\n")
    return "\n".join(lines)


def position_to_notch(pos, notches):
    idx = int(round(pos)) - 1
    idx = max(0, min(len(notches) - 1, idx))
    return notches[idx]


def judge(d, item_id, reply, table=None, spec=None, model=JUDGE_MODEL):
    """Score one reply for the dial configured in <dir>."""
    spec = spec or load_spec(d)
    table = table or load_table(d)
    notches = spec["notches"]
    item = table["items"][str(item_id)]
    prompt = JUDGE_TEMPLATE.format(
        prompt=item["prompt"],
        n=len(notches),
        noun=spec["judge_noun"],
        axis=spec["axis"],
        exemplar_block=_exemplar_block(item, notches),
        reply=reply,
    )
    ok, payload = call_claude(prompt, model, system=spec["judge_system"])
    if not ok:
        return {"ok": False, "error": payload}
    parsed = extract_json(payload)
    if not parsed or "position" not in parsed:
        return {"ok": False, "error": f"no position in: {payload[:200]}"}
    try:
        pos = float(parsed["position"])
    except (TypeError, ValueError):
        return {"ok": False, "error": f"bad position: {parsed.get('position')!r}"}
    pos = max(1.0, min(float(len(notches)), pos))
    return {
        "ok": True,
        "position": round(pos, 2),
        "notch": position_to_notch(pos, notches),
        "rationale": str(parsed.get("rationale", ""))[:300],
        "judge_version": JUDGE_VERSION,
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=".")
    args = ap.parse_args()
    spec = load_spec(args.dir)
    table = load_table(args.dir)
    first = sorted(table["items"], key=int)[0]
    top = spec["notches"][-1]
    demo = table["items"][first]["exemplars"][top]
    print(f"judging item #{first} '{top}' exemplar against itself:")
    print(json.dumps(judge(args.dir, first, demo, table, spec), indent=2, ensure_ascii=False))
