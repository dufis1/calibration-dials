---
name: calibrate-studio
description: Author, validate, and manage custom interaction dials for /calibrate. Use when the user types /calibrate-studio or asks to create their own dial, add a new dial/notch, or run the eval loop on a custom dial. Owns the author -> validate -> promote lifecycle; custom dials render in /calibrate automatically.
---

# Calibrate Studio — author your own dials

`/calibrate` ships five **validated** dials. This skill lets a user add their **own**
dials and harden them with the same eval loop that validated the five. A custom dial
moves through a lifecycle: **author → (optionally) validate → promote**.

The two skills share one registry — `levers.user.json`, which lives inside the sibling
`calibrate` skill. `studio.py` writes it (resolving it as a sibling of its own dir, so it
works the same whether installed as a plugin or copied under `~/.claude/skills/`);
`/calibrate`'s `dials.py` reads it from next to itself. So the moment a dial is
authored it renders in `/calibrate` (tagged **custom**, and **unvalidated** until it
passes the eval). Trust rule: **never describe an unvalidated dial as validated**, and
never hand-edit the registry or a `CLAUDE.md` block — go through the scripts.

Read `AUTHORING.md` (next to this file) before drafting any dial — it is the hardening
checklist you apply and self-check against.

Pick the branch that matches the user's intent.

---

## A. Author a new dial ("create a dial", "add a dial")

You interview the user, then **you draft** the dial (don't make them write directives).

1. **Interview.** Collect: the dial **name**; the **axis** it varies (one phrase,
   low → high); the **notch labels** in order (2–4; three is the norm — two poles + a
   middle); and the user's **intent** for each notch.
2. **Draft, applying `AUTHORING.md`.** Write, for each notch, a firm/concrete/mandatory
   **directive** (state the floor; bound any middle notch by naming its neighbors as
   walls) and a short one-line **blurb** for the widget hover. Draft the **judge system
   line** ("You score ONE thing: <axis> on a 1-N scale. You ignore everything else.").
   Pick 2–3 **domains** where the dial may behave differently, each mapped to a group.
3. **Review with the user.** Show the drafted directives and blurbs; revise on feedback.
4. **Write it.** Assemble this JSON and create the entry:

   ```json
   {
     "dial": "Verbosity",
     "slug": "verbosity",
     "axis": "how much the answer elaborates (low = bare, high = expansive)",
     "judge_system": "You are a careful evaluator. You score ONE thing: how much a response elaborates beyond the minimal answer, on a 1-3 scale. You ignore correctness, tone, and formatting.",
     "judge_noun": "Verbosity",
     "order": ["Terse", "Medium", "Verbose"],
     "notches": {
       "Terse":   {"directive": "...", "blurb": "..."},
       "Medium":  {"directive": "...", "blurb": "..."},
       "Verbose": {"directive": "...", "blurb": "..."}
     },
     "domains": {"Technical": "technical", "Personal advice": "personal"}
   }
   ```

   Write it to a temp file and run:

   ```
   python3 "${CLAUDE_PLUGIN_ROOT:-$HOME/.claude}/skills/calibrate-studio/studio.py" create --spec /tmp/dial.json
   ```

5. **Confirm in one line** that the dial was created (unvalidated) and now appears in
   `/calibrate`. Offer the validate branch as the next step — but it is optional; an
   unvalidated dial is fully usable, just unproven.

---

## B. Validate a dial ("validate <dial>", "harden my dial")

This runs the real judged pilot. It is the only part that spends quota, so gate it.

1. **Scaffold the pilot.**

   ```
   python3 "${CLAUDE_PLUGIN_ROOT:-$HOME/.claude}/skills/calibrate-studio/studio.py" scaffold-eval <dial-or-slug>
   ```
   This writes `dialspec.json` + a `pilot.md` stub of item skeletons under the pilot dir.

2. **Draft the battery (you, applying `AUTHORING.md`).** Edit `pilot.md`: for each item
   write a realistic prompt in its domain and one exemplar per notch, **length-matched
   within the item** (pad shorter exemplars with on-axis content). Have the user skim it.

3. **Freeze + audit (no quota):**

   ```
   python3 "${CLAUDE_PLUGIN_ROOT:-$HOME/.claude}/skills/calibrate-studio/eval/build_exemplars.py" --dir <pilot_dir>
   ```
   Rebalance any length-match FLAG (unless the dial's axis literally is length —
   then flags are expected; see `AUTHORING.md`).

4. **Judge self-test GATE (small quota — round-trips the exemplars):**

   ```
   python3 "${CLAUDE_PLUGIN_ROOT:-$HOME/.claude}/skills/calibrate-studio/eval/judge_selftest.py" --dir <pilot_dir>
   ```
   It must print **PASS**. If it FAILs, the ruler is broken — fix exemplars / the judge
   system line and repeat 3–4. **Do not sample until this passes.**

5. **BUDGET GATE — confirm before sampling.** Sampling shells out to `claude -p` under
   **subscription auth** (no API, no per-token billing); each sample costs ~2 `claude -p`
   calls (one to sample Sonnet, one to judge with Opus). State the rough count to the user
   — `notches × items × N × 2` calls — and get an explicit go-ahead. Run it **live in this
   session** (a scheduled/background run can't answer permission prompts). Start small:

   ```
   python3 -u "${CLAUDE_PLUGIN_ROOT:-$HOME/.claude}/skills/calibrate-studio/eval/run_pilot.py" --dir <pilot_dir> --n 5 --items 1 3
   ```
   Re-run to resume (it's resumable); `--summary-only` recomputes the verdict.

6. **Read the verdict + promote.** The run prints per-domain hit-rates, the staircase,
   and `overall_pass`. On pass:

   ```
   python3 "${CLAUDE_PLUGIN_ROOT:-$HOME/.claude}/skills/calibrate-studio/studio.py" promote <dial-or-slug>
   ```
   This flips `status` → `validated`, stores the verdict, and drops the "unvalidated" tag
   in `/calibrate`. If it did **not** pass, report which notch/domain fell short, revise
   that directive (bump `directive_version` in `dialspec.json`) and re-run, or accept the
   limit and surface it as lower confidence. Do not `--force` a failing promotion.

---

## C. Manage dials ("list / show / remove dials")

```
python3 "${CLAUDE_PLUGIN_ROOT:-$HOME/.claude}/skills/calibrate-studio/studio.py" list
python3 "${CLAUDE_PLUGIN_ROOT:-$HOME/.claude}/skills/calibrate-studio/studio.py" show <dial-or-slug>
python3 "${CLAUDE_PLUGIN_ROOT:-$HOME/.claude}/skills/calibrate-studio/studio.py" remove <dial-or-slug>
```
After `remove`, the dial stops rendering in `/calibrate`, and its directive clears from
`CLAUDE.md` on the next `/calibrate` apply.

---

## Files (this skill dir — `skills/calibrate-studio/` in the plugin, or `~/.claude/skills/calibrate-studio/` if copied manually)
- `studio.py` — registry (create/list/show/remove/promote) + `scaffold-eval`.
- `eval/` — the parameterized judged-pilot harness (`build_exemplars.py`, `judge.py`,
  `judge_selftest.py`, `run_pilot.py`, shared `harness.py`). Config-driven: everything
  dial-specific is read from the pilot dir's `dialspec.json`.
- `AUTHORING.md` — the hardening checklist (read before drafting).
- `pilots/user-<slug>/` — per-dial eval artifacts (created by `scaffold-eval`).
