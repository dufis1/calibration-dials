"""HARD GATE before any model sampling (generalized from pilot/rigor/judge_selftest.py).

If the judge cannot sort its own frozen exemplars back onto their notches, the ruler
is broken and no downstream number means anything — so this runs FIRST and must pass.

Three checks:
  (a) ROUND-TRIP: feed each exemplar back through judge() as if it were a reply;
      expect notch == its own notch and |position - target| <= POS_TOL.
  (b) ADJACENT SEPARABILITY: adjacent notches must not cross-classify, and there must
      be zero distance>=2 ("far") confusions.
  (c) STABILITY: `claude -p` has no temperature flag, so judge a subset REPEATS times
      and report position variance; a high-variance judge is itself a gate failure.

GATE: round-trip accuracy >= GATE_ACC (0.875) AND adjacency clean.

Run:
  python3 judge_selftest.py --dir <pilot_dir>
  python3 judge_selftest.py --dir <pilot_dir> --repeats 3
  python3 judge_selftest.py --dir <pilot_dir> --items 1 5 9
"""
import argparse
import statistics
import sys
from collections import defaultdict

from harness import GATE_ACC, POS_TOL, STABILITY_SD, JUDGE_VERSION
from judge import judge, load_table, load_spec


def round_trip(d, items, table, notches, target):
    print(f"=== ROUND-TRIP (judge_version={JUDGE_VERSION}, tol=±{POS_TOL}) ===")
    confusion = defaultdict(lambda: defaultdict(int))
    correct = total = 0
    pos_err, offdiag, errors = [], [], []
    for item_id in items:
        ex = table["items"][str(item_id)]["exemplars"]
        for true_notch in notches:
            r = judge(d, item_id, ex[true_notch], table)
            if not r["ok"]:
                errors.append(f"#{item_id} {true_notch}: {r['error']}")
                continue
            total += 1
            pred = r["notch"]
            confusion[true_notch][pred] += 1
            pos_err.append(abs(r["position"] - target[true_notch]))
            if pred == true_notch:
                correct += 1
            else:
                offdiag.append(f"#{item_id} {true_notch} -> {pred} "
                               f"(pos {r['position']}: {r['rationale']})")
    print(f"\nround-trip: {correct}/{total} exemplars classify onto their own notch")
    if pos_err:
        print(f"mean |position error|: {sum(pos_err)/len(pos_err):.2f}")
    print("\nconfusion (rows = true notch, cols = predicted):")
    print("             " + "".join(f"{n[:4]:>7}" for n in notches))
    for tn in notches:
        row = "".join(f"{confusion[tn].get(pn, 0):>7}" for pn in notches)
        print(f"  {tn:<11}{row}")
    if offdiag:
        print("\noff-diagonal (misclassified exemplars):")
        for o in offdiag:
            print("  -", o)
    if errors:
        print("\nJUDGE CALL ERRORS:")
        for e in errors:
            print("  -", e)
    return correct, total, confusion


def adjacency_check(confusion, notches):
    print("\n=== ADJACENT SEPARABILITY ===")
    ok = True
    for i in range(len(notches) - 1):
        a, b = notches[i], notches[i + 1]
        ab = confusion[a].get(b, 0)
        ba = confusion[b].get(a, 0)
        bad = " ✗" if (ab + ba) > 0 else " ✓"
        if (ab + ba) > 0:
            ok = False
        print(f"  {a} <-> {b}: {a}->{b}={ab}, {b}->{a}={ba}{bad}")
    order = {n: i for i, n in enumerate(notches)}
    far = sum(confusion[tn].get(pn, 0)
              for tn in notches for pn in notches
              if abs(order[tn] - order[pn]) >= 2)
    print(f"  non-adjacent confusions (distance>=2): {far}" + (" ✗" if far else " ✓"))
    return ok and far == 0


def stability(d, items, table, notches, repeats):
    print(f"\n=== STABILITY ({repeats} repeats; no temp control on `claude -p`) ===")
    worst = 0.0
    for item_id in items:
        ex = table["items"][str(item_id)]["exemplars"]
        for n in notches:
            positions = []
            for _ in range(repeats):
                r = judge(d, item_id, ex[n], table)
                if r["ok"]:
                    positions.append(r["position"])
            if len(positions) >= 2:
                sd = statistics.pstdev(positions)
                worst = max(worst, sd)
                mark = " ✗" if sd > STABILITY_SD else ""
                print(f"  #{item_id} {n:<11} positions {min(positions)}-{max(positions)} (sd {sd:.2f}){mark}")
    print(f"\nworst within-cell sd: {worst:.2f}" +
          ("  ✗ judge is noisy" if worst > STABILITY_SD else "  ✓ acceptably stable"))
    return worst


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=".")
    ap.add_argument("--items", type=int, nargs="+")
    ap.add_argument("--repeats", type=int, default=1)
    args = ap.parse_args()

    spec = load_spec(args.dir)
    notches = spec["notches"]
    target = {n: i + 1 for i, n in enumerate(notches)}
    table = load_table(args.dir)
    all_items = sorted(int(k) for k in table["items"])
    items = args.items or all_items

    correct, total, confusion = round_trip(args.dir, items, table, notches, target)
    sep_ok = adjacency_check(confusion, notches)

    stable_ok = True
    if args.repeats > 1:
        sub = items if args.items else [items[0], items[len(items)//2], items[-1]]
        stable_ok = stability(args.dir, sub, table, notches, args.repeats) <= STABILITY_SD

    acc = correct / total if total else 0
    gate = acc >= GATE_ACC and sep_ok and stable_ok
    print("\n" + "=" * 56)
    print(f"GATE: round-trip {acc:.0%}, adjacency {'clean' if sep_ok else 'BROKEN'}"
          f"  ->  {'PASS — safe to sample' if gate else 'FAIL — fix exemplars/judge before sampling'}")
    sys.exit(0 if gate else 1)


if __name__ == "__main__":
    main()
