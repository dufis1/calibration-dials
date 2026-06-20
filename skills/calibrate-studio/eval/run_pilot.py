"""Config-driven judged-pilot runner (generalized from pilot/rigor/run_rigor_pilot.py).

Samples Sonnet via `claude -p` (subscription auth, default system prompt) with the
notch's directive injected exactly as the product does — a delimited block in a
temp-workdir CLAUDE.md — JUDGES each reply with Opus (judge.py), and emits
per-DOMAIN hit-rate verdicts plus a monotonic-staircase check. Per-domain, never
pooled: a genuinely bimodal dial pooled together reads as a false ~50% and looks
broken.

One steering condition per notch (target = its position on the scale). A custom dial
passes (`overall_pass`) when every notch clears the hit-rate bar in every domain that
has data AND every domain's mean positions rise monotonically across the notches.

Each model call shells out to `claude -p` (no API, no per-token billing); each sample
costs ~2 calls (sample + judge). Resumable: re-run to continue; `--summary-only`
recomputes the verdict from stored results.

Run:
    python3 -u run_pilot.py --dir <pilot_dir> --n 5 --items 1 4 7
    python3 -u run_pilot.py --dir <pilot_dir> --summary-only
"""
import argparse
import json
import os
import sys
import tempfile
import time
from collections import defaultdict, Counter

from harness import HIT_RATE_PASS, JUDGE_VERSION, SAMPLE_MODEL, JUDGE_MODEL, call_claude
from judge import judge, load_table, load_spec

MAX_CONSECUTIVE_ERRORS = 5
BACKOFF = [30, 60, 120, 240, 480]


def conditions_from_spec(spec):
    dver = spec.get("directive_version", "v1")
    return [{"name": n, "version": dver, "target": i + 1, "directive": spec["directives"][n]}
            for i, n in enumerate(spec["notches"])]


def results_path(d):
    return os.path.join(d, "results.jsonl")


def summary_path(d):
    return os.path.join(d, "summary.json")


def done_keys(d):
    keys = set()
    if not os.path.exists(results_path(d)):
        return keys
    with open(results_path(d), encoding="utf-8") as f:
        for line in f:
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("ok"):
                keys.add((r["condition"], r["version"], r["item"], r["sample"]))
    return keys


def append_result(d, rec):
    with open(results_path(d), "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def make_workdir(cond):
    wd = tempfile.mkdtemp(prefix="studio_eval_")
    with open(os.path.join(wd, "CLAUDE.md"), "w", encoding="utf-8") as f:
        f.write("<!-- dial-settings:start -->\n" + cond["directive"]
                + "\n<!-- dial-settings:end -->\n")
    return wd


def run(d, spec, table, items, conditions, n, model, judge_model, sleep):
    done = done_keys(d)
    consecutive = 0
    for cond in conditions:
        wd = make_workdir(cond)
        for item_id in items:
            prompt = table["items"][str(item_id)]["prompt"]
            domain = table["items"][str(item_id)]["domain"]
            for s in range(n):
                if (cond["name"], cond["version"], item_id, s) in done:
                    continue
                ok, reply = call_claude(prompt, model, cwd=wd)
                if not ok:
                    consecutive += 1
                    append_result(d, {"ok": False, "stage": "sample", "condition": cond["name"],
                                      "version": cond["version"], "item": item_id, "sample": s,
                                      "error": reply})
                    print(f"  SAMPLE ERROR {cond['name']} #{item_id} s{s}: {reply}", file=sys.stderr)
                    if consecutive >= MAX_CONSECUTIVE_ERRORS:
                        print("\nStopping: too many consecutive errors. Re-run to resume.", file=sys.stderr)
                        return
                    time.sleep(BACKOFF[min(consecutive - 1, len(BACKOFF) - 1)])
                    continue
                jr = judge(d, item_id, reply, table, spec, model=judge_model)
                if not jr["ok"]:
                    consecutive += 1
                    append_result(d, {"ok": False, "stage": "judge", "condition": cond["name"],
                                      "version": cond["version"], "item": item_id, "sample": s,
                                      "error": jr["error"]})
                    print(f"  JUDGE ERROR {cond['name']} #{item_id} s{s}: {jr['error']}", file=sys.stderr)
                    if consecutive >= MAX_CONSECUTIVE_ERRORS:
                        print("\nStopping: too many consecutive errors. Re-run to resume.", file=sys.stderr)
                        return
                    time.sleep(BACKOFF[min(consecutive - 1, len(BACKOFF) - 1)])
                    continue
                append_result(d, {"ok": True, "condition": cond["name"], "version": cond["version"],
                                  "item": item_id, "domain": domain, "sample": s,
                                  "position": jr["position"], "notch": jr["notch"],
                                  "rationale": jr["rationale"],
                                  "exemplar_version": table.get("exemplar_version"),
                                  "judge_version": jr["judge_version"], "reply": reply})
                consecutive = 0
                print(f"  {cond['name']:>16} #{item_id} ({domain[:4]}) s{s}: pos {jr['position']} ({jr['notch']})")
                if sleep:
                    time.sleep(sleep)
    print("\nrun complete.")


def summarize(d, spec, table, conditions):
    if not os.path.exists(results_path(d)):
        print("no results yet.")
        return
    notches = spec["notches"]
    domain_group = spec["domains"]
    groups = sorted(set(domain_group.values()))
    cur_ver = {c["name"]: c["version"] for c in conditions}
    cur_exv = table.get("exemplar_version")

    by = defaultdict(lambda: defaultdict(list))   # condition -> group -> [(pos, notch)]
    with open(results_path(d), encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            if not r.get("ok"):
                continue
            if r.get("version") != cur_ver.get(r["condition"]):
                continue
            if r.get("exemplar_version") != cur_exv or r.get("judge_version") != JUDGE_VERSION:
                continue
            grp = domain_group.get(r.get("domain"), "?")
            by[r["condition"]][grp].append((r["position"], r["notch"]))

    print(f"\n=== PER-DOMAIN HIT-RATE VERDICTS (pass >= {HIT_RATE_PASS:.0%} in target notch) ===")
    summary = {"dial": spec["dial"], "hit_rate_pass": HIT_RATE_PASS,
               "judge_version": JUDGE_VERSION, "exemplar_version": cur_exv, "conditions": {}}
    means = defaultdict(dict)
    notch_pass = True
    for cond in conditions:
        name, tnotch = cond["name"], notches[cond["target"] - 1]
        print(f"\n  {name}  (target {tnotch})")
        summary["conditions"][name] = {}
        for grp in groups:
            s = by[name].get(grp, [])
            if not s:
                print(f"     {grp:>10}: — (no data)")
                continue
            mean = sum(p for p, _ in s) / len(s)
            means[name][grp] = mean
            hits = sum(1 for _, nt in s if nt == tnotch)
            hr = hits / len(s)
            ok = hr >= HIT_RATE_PASS
            notch_pass = notch_pass and ok
            print(f"     {grp:>10}: hit-rate {hr*100:3.0f}% {'✓' if ok else '✗'}  (mean {mean:.2f}, n={len(s)})")
            summary["conditions"][name][grp] = {"hit_rate": round(hr, 2), "mean": round(mean, 2),
                                                "n": len(s), "pass": ok}

    print("\n  staircase (mean position, should rise across notches):")
    stair_ok = True
    summary["staircase"] = {}
    for grp in groups:
        seq = [means[c["name"]].get(grp) for c in conditions if grp in means.get(c["name"], {})]
        mono = all(seq[i] < seq[i + 1] for i in range(len(seq) - 1)) if len(seq) > 1 else None
        if mono is False:
            stair_ok = False
        print(f"    {grp:>10}: {[round(x, 2) for x in seq]}  ->  "
              f"{'✓ monotonic' if mono else '✗ NOT monotonic' if mono is False else 'n/a'}")
        summary["staircase"][grp] = {"means": [round(x, 2) for x in seq], "monotonic": mono}

    summary["overall_pass"] = bool(notch_pass and stair_ok)
    with open(summary_path(d), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print(f"\n  overall: {'✓ PASS — eligible to promote to validated' if summary['overall_pass'] else '✗ not yet — inspect rationales in results.jsonl, revise a directive (bump directive_version), or accept + surface lower confidence'}")
    print(f"  -> {summary_path(d)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=".")
    ap.add_argument("--n", type=int, default=5)
    ap.add_argument("--items", type=int, nargs="+")
    ap.add_argument("--model", default=SAMPLE_MODEL)
    ap.add_argument("--judge-model", default=JUDGE_MODEL)
    ap.add_argument("--sleep", type=float, default=0.0)
    ap.add_argument("--summary-only", action="store_true")
    args = ap.parse_args()

    spec = load_spec(args.dir)
    table = load_table(args.dir)
    conditions = conditions_from_spec(spec)
    all_items = sorted(int(k) for k in table["items"])
    items = args.items or all_items

    if not args.summary_only:
        print(f"dial '{spec['dial']}' | items {items} | N={args.n} | model {args.model} | judge {args.judge_model}\n"
              f"notches {spec['notches']}")
        run(args.dir, spec, table, items, conditions, args.n, args.model, args.judge_model, args.sleep)
    summarize(args.dir, spec, table, conditions)


if __name__ == "__main__":
    main()
