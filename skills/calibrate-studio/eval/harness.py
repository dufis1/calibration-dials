"""Shared helpers for the parameterized judged-pilot harness (/calibrate-studio).

This is a config-driven generalization of the reference pilots in
calibration-dials/pilot/{rigor,autonomy,tone}/. Instead of hardcoding NOTCHES,
the steering directives, the domain map, and the judge's confound-control system
line per dial, every script here reads them from a `dialspec.json` that lives in
the per-dial pilot directory (scaffolded by studio.py).

It is intentionally self-contained (its own token counter, its own `claude -p`
wrapper) so the studio skill deploys to ~/.claude/skills/calibrate-studio/ without
depending on the eval-repo's pilot/ tree.

All model calls shell out to `claude -p` under subscription auth — no API keys, no
per-token billing. `claude -p` exposes no temperature flag, so judge_selftest.py
*measures* stability rather than assuming determinism (same honest substitute the
reference pilots use).
"""
import json
import os
import re
import subprocess

# Gate + verdict thresholds — kept identical to the reference pilots so a custom
# dial is held to the same bar as the built-in five.
POS_TOL = 0.75          # round-trip |measured - target| must be within this
GATE_ACC = 0.875        # round-trip accuracy gate (>=7/8 per notch-ish)
STABILITY_SD = 0.5      # worst within-cell judge sd above this = noisy judge
HIT_RATE_PASS = 0.70    # per-domain hit-rate to pass a notch
LENGTH_RATIO_FLAG = 1.5 # within an item, max/min exemplar token ratio above this -> flag
JUDGE_VERSION = "v1"
JUDGE_MODEL = "opus"
SAMPLE_MODEL = "sonnet"


# ----- dialspec ------------------------------------------------------------

REQUIRED_SPEC_KEYS = ("dial", "notches", "axis", "judge_system", "directives", "domains")


def load_spec(d):
    """Load and validate <dir>/dialspec.json. `notches` is ordered low->high."""
    path = os.path.join(d, "dialspec.json")
    with open(path, encoding="utf-8") as f:
        spec = json.load(f)
    missing = [k for k in REQUIRED_SPEC_KEYS if k not in spec]
    if missing:
        raise SystemExit(f"dialspec.json missing required keys: {missing}")
    n = spec["notches"]
    if len(n) < 2:
        raise SystemExit("a dial needs at least 2 notches")
    for label in n:
        if label not in spec["directives"]:
            raise SystemExit(f"notch '{label}' has no directive in dialspec.json")
    spec.setdefault("judge_noun", spec["dial"])
    spec.setdefault("exemplar_version", "v1")
    return spec


# ----- token counting (for the length-match audit) -------------------------

def tokenizer_name():
    try:
        import tiktoken  # noqa: F401
        return "tiktoken:cl100k_base"
    except Exception:
        return "approx:chars/4"


def count_tokens(text):
    try:
        import tiktoken
        return len(tiktoken.get_encoding("cl100k_base").encode(text))
    except Exception:
        return max(1, round(len(text) / 4))


# ----- claude -p wrapper ---------------------------------------------------

def call_claude(prompt, model, system=None, cwd=None, timeout=180):
    """Run `claude -p` (subscription auth). Returns (ok, text_or_error)."""
    cmd = ["claude", "-p", "--model", model]
    if system:
        cmd += ["--append-system-prompt", system]
    cmd += ["--output-format", "json", prompt]
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, "timeout"
    try:
        j = json.loads(p.stdout.strip())
    except ValueError:
        return False, f"unparseable: {p.stdout[:200] or p.stderr[:200]}"
    if j.get("is_error") or j.get("api_error_status"):
        return False, f"api_error: {j.get('api_error_status')} {j.get('subtype')}"
    return True, j.get("result", "")


def extract_json(text):
    """Pull the first {...} object out of the model's text."""
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except ValueError:
        return None
