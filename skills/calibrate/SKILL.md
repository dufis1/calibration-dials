---
name: calibrate
description: Calibrate Claude's interaction style (Claude Code). Use when the user types /calibrate or asks to calibrate Claude's interaction style. Renders five interaction dials and persists the selection as a Claude Code output style so future sessions obey.
---

# Calibrate (Claude Code)

> **ℹ️ Two surfaces.** This skill renders an interactive HTML **widget** in the Claude Code
> **desktop app**. **Terminal Claude Code has no widget surface**, so there you fall back to
> an **arrow-key picker** (the AskUserQuestion menu). Always run `dials.py surface` first
> (step 1) and branch on the result — never print the raw HTML on the picker surface, and
> never pretend a widget rendered when it didn't.

Five dials, each with three notches, let the user steer Claude's interaction style.
A dial left **unset** uses Claude's default behavior for that axis — the user only
overrides the dials they care about. Persistence is handled by a deterministic
script (`dials.py`); you render the widget, run the script, and narrate the result.

The selection is saved as a Claude Code **output style** named `Calibrated` (the
combined directives live in `output-styles/calibrated.md` and are activated via the
`outputStyle` setting). Because an output style is part of the system prompt — read
once at session start — a change **takes effect after `/clear` or a new session**.
`dials.py` handles all of this; you never touch the files by hand.

Power users can author their **own** dials — and harden them with the same eval loop
that validated these five — via `/calibrate-studio`. Any custom dials they create render
in this widget automatically (tagged **custom**, plus **unvalidated** until they pass the
eval), so you do not hardcode them; they arrive through the `userdials` step below.

When invoked:

1. **Pre-seed, then render the widget.** First run the reader to find what's already applied:

   ```
   python3 "${CLAUDE_PLUGIN_ROOT:-$HOME/.claude}/skills/calibrate/dials.py" read
   ```
   (add `--global` to read the user-level output style in `~/.claude/`.) It prints a
   JSON object of currently-applied dial→notch labels — e.g.
   `{"Detail": "Brief", "Tone": "Casual"}` — or `{}` when nothing is set yet
   (first-time use, or the user has switched to a different output style).

   Then read any **custom dials** the user authored via `/calibrate-studio`:

   ```
   python3 "${CLAUDE_PLUGIN_ROOT:-$HOME/.claude}/skills/calibrate/dials.py" userdials
   ```
   (same `--global` rule.) It prints a JSON array — `[]` when there are none, or e.g.
   `[{"name":"Verbosity","status":"unvalidated","stops":[["Terse","One sentence…"]]}]`.

   Then detect whether this surface can render the interactive widget:

   ```
   python3 "${CLAUDE_PLUGIN_ROOT:-$HOME/.claude}/skills/calibrate/dials.py" surface
   ```
   It prints **`widget`** (the Claude Code desktop app — can render HTML) or **`picker`**
   (terminal Claude Code and any other surface with no widget rendering). Branch on it:

   - **`widget`** → render the HTML below **verbatim, with two substitutions**: replace
     `__PRESEED__` with the first JSON object and `__USERDIALS__` with the second JSON
     array. Change nothing else — not the labels, not the logic. `sendToClaude(text)` is
     already wired to `sendPrompt`.
   - **`picker`** → **do NOT print the HTML** (it would show as raw code and be unusable).
     Use the **arrow-key picker fallback** described just after the HTML block instead.

   ```html
   <!DOCTYPE html>
   <html><head><meta charset="utf-8"><style>
   body{font-family:system-ui,sans-serif;margin:0;padding:16px;color:#111;background:#fff;}
   .dial{padding-top:13px;margin-bottom:13px;border-top:1px solid #ececec;}
   .dial.first{border-top:none;padding-top:0;}
   .row{display:grid;grid-template-columns:108px 1fr;align-items:center;gap:12px;}
   .name{font-size:14px;font-weight:600;}
   .seg{display:flex;border:1px solid #ccc;border-radius:8px;overflow:hidden;}
   .sg{flex:1;text-align:center;padding:8px 6px;font-size:13px;cursor:pointer;transition:background .12s;}
   .sg+.sg{border-left:1px solid #ccc;}
   .sg:not(.sel):hover{background:rgba(217,119,87,.10);}
   .sg.sel{background:rgba(217,119,87,.16);color:#b5502e;font-weight:600;}
   .desc{font-size:12px;color:#999;min-height:17px;line-height:1.4;}
   .desc.on{color:#b5502e;}
   .tags{margin-top:3px;}
   .chip{display:inline-block;margin-right:4px;padding:1px 5px;border-radius:5px;font-size:9px;font-weight:600;background:#eee;color:#777;}
   .chip.warn{background:rgba(217,119,87,.14);color:#b5502e;}
   #apply{display:block;margin:18px auto 0;padding:9px 22px;background:#D97757;color:#fff;border:1px solid #D97757;border-radius:8px;cursor:pointer;font-size:14px;}
   #out{margin-top:10px;font-size:12px;color:#777;text-align:center;}
   </style></head><body>
   <div id="card"></div>
   <button id="apply">Apply</button>
   <div id="out"></div>
   <script>
   function sendToClaude(text){ if(typeof sendPrompt==='function') return sendPrompt(text); }
   const PRESEED=__PRESEED__;
   const DIALS=[
    {name:'Detail',sel:-1,stops:[
      ['Brief','3–4 sentences — the bottom line plus only the essentials.'],
      ['Standard','About two short paragraphs — main points and key caveats.'],
      ['Exhaustive','Full coverage — edge cases, caveats, and tangents.']]},
    {name:'Presentation',sel:-1,stops:[
      ['Pure prose','Flowing paragraphs only — no headings, lists, or bold.'],
      ['Light structure','Prose-first, with bold key terms and one short list.'],
      ['Heavy structure','Scannable document — headings, lists, and a table.']]},
    {name:'Tone',sel:-1,stops:[
      ['Formal','Professional and composed — precise, no slang or contractions.'],
      ['Conversational','Natural and plain-spoken — warm but focused.'],
      ['Casual','Relaxed and informal — contractions, asides, the odd joke.']]},
    {name:'Rigor',sel:-1,stops:[
      ['Affirming','Takes your side — validates and builds on the idea.'],
      ['Balanced','Even-handed — the real strengths and the real weaknesses.'],
      ['Adversarial','Stress-tests it — actively tries to break the idea.']]},
    {name:'Autonomy',sel:-1,stops:[
      ['Confirm each step','Asks questions, proposes a plan, waits for sign-off.'],
      ['Check key decisions','Asks the one pivotal question, proceeds on minor calls.'],
      ['Run with it','Makes reasonable assumptions and delivers the whole thing.']]}
   ];
   const USERDIALS=__USERDIALS__;
   USERDIALS.forEach(u=>{DIALS.push({name:u.name,sel:-1,stops:u.stops,custom:true,status:u.status});});
   DIALS.forEach(d=>{d.sel=d.stops.findIndex(s=>s[0]===PRESEED[d.name]);});
   const card=document.getElementById('card');
   function render(){
    let h='';
    DIALS.forEach((d,di)=>{
     h+='<div class="dial'+(di===0?' first':'')+'">'
      +'<div class="row"><div class="name">'+d.name+(d.custom?'<div class="tags"><span class="chip">custom</span>'+(d.status==='unvalidated'?'<span class="chip warn">unvalidated</span>':'')+'</div>':'')+'</div>'
      +'<div class="seg">'+d.stops.map((s,p)=>'<div class="sg'+(d.sel===p?' sel':'')+'" data-di="'+di+'" data-p="'+p+'">'+s[0]+'</div>').join('')+'</div></div>'
      +'<div class="row"><div></div>'
      +'<div class="desc'+(d.sel>=0?' on':'')+'" data-di="'+di+'">'+(d.sel>=0?d.stops[d.sel][1]:'Hover a notch to see what it does.')+'</div></div>'
      +'</div>';
    });
    card.innerHTML=h;
    const descs=card.querySelectorAll('.desc');
    card.querySelectorAll('.sg').forEach(t=>{
     const di=+t.dataset.di,p=+t.dataset.p;
     t.addEventListener('mouseenter',()=>{descs[di].textContent=DIALS[di].stops[p][1];descs[di].classList.add('on');});
     t.addEventListener('mouseleave',()=>{const d=DIALS[di];descs[di].textContent=d.sel>=0?d.stops[d.sel][1]:'Hover a notch to see what it does.';descs[di].classList.toggle('on',d.sel>=0);});
     t.addEventListener('click',()=>{const d=DIALS[di];d.sel=(d.sel===p?-1:p);render();});
    });
   }
   render();
   document.getElementById('apply').addEventListener('click',()=>{
    const set=DIALS.filter(d=>d.sel>=0);
    const line=set.length?('Calibrate: '+set.map(d=>d.name+' = '+d.stops[d.sel][0]).join(', ')):'Calibrate: reset — all dials to default';
    sendToClaude(line);
    document.getElementById('out').textContent='Sent.';
   });
   </script></body></html>
   ```

   **Picker fallback (only when `surface` printed `picker`).** There is no widget surface,
   so build the picker with the **AskUserQuestion** tool — it gives the user an arrow-key /
   number-key selectable menu, no hand-typing. Do not print the HTML.
   - **One question per dial**, for all five built-ins plus any custom dials from the
     `userdials` array. For each dial: **question** = the dial name + what it controls,
     noting its current value if the `read` pre-seed has one ("Rigor — currently Balanced");
     **header** = the dial name (≤12 chars); **options** = its notches in order, using the
     **labels and one-line descriptions from the `DIALS` array above** (custom dials: from
     their `userdials` stops); **multiSelect** = false.
   - For a 2–3-notch dial, add a final option **"Leave default"** ("Use Claude's default for
     this axis"). A 4-notch custom dial already fills the 4-option limit — omit it; the user
     can pick **Other → "skip"** to leave that dial unset.
   - **Batch in calls of up to 4 questions** (the tool's max): the five built-ins take two
     calls (4 + 1); put custom dials in a further call.
   - **Build the apply line from the answers**: list **only** dials where the user chose a
     real notch — drop any "Leave default" / "skip". Format it exactly like the widget's,
     e.g. `Detail = Brief, Tone = Casual`; if no real notch was chosen anywhere, use
     `reset — all dials to default`. Then go to step 3.
   - If AskUserQuestion is somehow unavailable, degrade to a plain numbered list (print each
     dial and its numbered notches; ask the user to reply with picks like "Detail 1, Tone 3")
     and build the same line.

2. **Get the `Calibrate:` line.** The desktop widget's Apply button sends one; on the
   picker path **you build the same line** from the answers (step 1). Either way it lists
   **only the dials the user set** — e.g. `Calibrate: Detail = Brief, Tone = Casual` — or `Calibrate: reset — all dials to default` when they cleared everything. Any dial **not listed** is intentionally left at Claude's default. Read the labels **literally** — never translate, infer, or add a notch the user didn't pick.

3. **Persist with the script — do not hand-edit the output style or settings.** Run:

   ```
   python3 "${CLAUDE_PLUGIN_ROOT:-$HOME/.claude}/skills/calibrate/dials.py" apply "<everything after 'Calibrate: '>"
   ```
   (add `--global` to target the user level, `~/.claude/`.) Pass the text through
   verbatim. The script deterministically (re)writes the `Calibrated` **output style**
   — `output-styles/calibrated.md` — with the validated directive for each **listed**
   dial (from `levers.json`, the single source of truth), **omitting every dial the user
   did not list**, and activates it by setting `outputStyle: "Calibrated"` in the
   settings file. On a full reset it removes the style file and deactivates it (without
   disturbing a different output style the user may have set, or any other settings key).
   If the script prints `ERROR`, surface it and stop — nothing was written.

4. **Report — confirm what was saved, plus the one functional note.** Echo the script's
   result in a single line, e.g. "Saved as the Calibrated output style — Detail = Brief,
   Tone = Casual (other dials left at default)." Then add the **one** required line: it
   takes effect after **`/clear` or a new session** (an output style is part of the
   system prompt). Do **not** add caveats, confidence notes, reliability percentages, or
   any commentary about the dials or how they interact. Confirm and stop.

## Validation provenance
The directive text in `levers.json` is eval-confirmed per dial — see
`calibration-dials/pilot/length/` (Detail), `pilot/style/` (Presentation),
`pilot/rigor/`, `pilot/autonomy/`, and `pilot/tone/`. Pilot directories keep their
original on-disk names.
