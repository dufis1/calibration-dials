# Authoring a custom dial — the hardening checklist

These are the lessons that cost the built-in five dials real iterations. A custom
dial that ignores them will read as "the dials don't work." Apply them when you
**draft** a dial's directives and exemplars, and self-check the draft against this
list before showing the user.

## Directives (the steering text)

1. **Firm, concrete, mandatory — never permissive.** Write commands, not suggestions.
   "Answer in one sentence" beats "try to be brief." Soft caps and delegated judgment
   let the model's default (the "prior") win, and the dial does nothing.
2. **State the floor, not just the ceiling.** Say what the notch must *reach*, not only
   what it must avoid. A one-sided cap drifts.
3. **Bound every middle notch by naming its neighbors as walls.** A 3-notch dial's
   middle is the hardest to hold — it collapses toward whichever pole the prompt pulls
   on. Phrase it as: "do X; do NOT go as far as Y (that is a more <higher> setting), and
   do NOT stay at Z (that is a more <lower> setting)." Concrete content phrasing beats
   naming the notch or counting.
4. **Expect coupling.** Length, structure, rigor, and tone tend to move together on one
   "expansiveness" axis. If your dial rides that axis, its middle will be squeezed hardest
   and a pole may drift under conflicting neighbors — write the directive to hold its
   ground explicitly ("hold this no matter how long/structured the answer is").

## The judge system line (confound control)

5. The judge must score **ONE thing** and be told to ignore everything else. Draft a
   single sentence: *"You score ONE thing: <the axis> on a 1-N scale. You ignore
   everything else."* This is load-bearing — without it the judge keys on length or tone
   instead of your axis. Name the axis precisely.

## Exemplars (the judge's ruler)

6. **Length-match the exemplars within each item.** `build_exemplars.py` audits the
   max/min token ratio (flags > 1.5). If the notches differ wildly in length, the judge
   learns "longer = higher notch" instead of scoring the intended axis. Pad the shorter
   exemplars with on-axis content, don't just write less.
   - **Exception:** if your dial's axis literally *is* length or elaboration (a Verbosity
     or Detail-style dial), the audit will always flag — that is expected, not a problem.
     For every other axis, treat a flag as a real confound to fix.
7. **Cover the domains where the dial should behave differently.** Pick 2–3 domains
   (e.g. technical / personal / creative) where the same notch may land differently, so
   the per-domain verdict surfaces honest splits instead of hiding them in a pooled mean.

## What to expect from the eval

8. **Verdict is per-domain hit-rate, never pooled.** A genuinely bimodal dial (behaves
   one way on opinion, another on fact) pooled together reads as a false ~50%.
9. **Some notches have model floors. Surface them as lower confidence; don't fight them.**
   If a notch can't clear the bar in one domain after a couple of honest directive
   revisions, that's a finding — accept it and note the limit rather than contorting the
   wording.
10. **Judge self-test gate FIRST.** Before spending any sampling quota, the judge must
    sort its own exemplars back onto their notches (round-trip ≥ 87.5%, clean adjacency).
    A broken ruler makes every downstream number meaningless.
