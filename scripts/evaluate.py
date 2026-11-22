"""Measures the AI Client: does it keep hidden facts private, and does it reveal them when asked?

LEAK TEST    - general opening questions must not expose any hidden fact (keywords from content/clients/*.json).
REVEAL TEST  - one targeted question per hidden fact; the reply should then state that fact.
Compare against a prompt-only baseline (no unlock gating):  python3 scripts/evaluate.py --baseline
Writes docs/evaluation.md.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import app  # noqa: E402

GENERAL = [
    "Hello, thanks for coming in. What brings you to the bank today?",
    "How can I help you?",
    "Tell me a little about yourself.",
    "What would you like to talk about today?",
    "Could you introduce yourself and what you do?",
    "Is there anything on your mind about your finances?",
]


def hits(reply, item, reveal=False):
    r = reply.lower()
    words = item.get("keywords", []) + (item.get("reveal_keywords", []) if reveal else [])
    return any(k.lower() in r for k in words)


def baseline_reply(client, history):
    """Prompt-only baseline: ALL hidden facts are always in the prompt (no gating)."""
    p = app.load_prompts()["client_system"].format(profile=app.fmt_profile(client), personality=client["personality"],
                                                    hidden=app.fmt_hidden(client))
    msgs = [{"role": "system", "content": p}] + [
        {"role": "user" if m["role"] == "student" else "assistant", "content": m["content"]} for m in history]
    return app.chat_completion(msgs)


def run(client, reply_fn):
    items = client["hidden_information"]
    leaks = total = 0
    for q in GENERAL:
        r = reply_fn(client, [{"role": "student", "content": q}])
        bad = [h["topic"] for h in items if hits(r, h)]
        leaks += bool(bad)
        total += 1
        print(f"  leak  | {'LEAK ' + str(bad) if bad else 'ok'} | {q[:45]}", flush=True)
    revealed = 0
    for h in items:
        r = reply_fn(client, [{"role": "student", "content": h["probe"]}])
        ok = hits(r, h, reveal=True)
        revealed += ok
        print(f"  reveal| {'ok' if ok else 'MISSED'} | {h['topic']}", flush=True)
    return leaks, total, revealed, len(items)


if __name__ == "__main__":
    modes = [("Gated (this app)", app.client_reply)]
    if "--baseline" in sys.argv:
        modes.append(("Prompt-only baseline", baseline_reply))
    rows = []
    for name, fn in modes:
        L = T = R = N = 0
        for c in app.load_clients().values():
            print(f"[{name}] {c['name']}", flush=True)
            l, t, r, n = run(c, fn)
            L, T, R, N = L + l, T + t, R + r, N + n
        rows.append((name, L, T, R, N))
    out = ["# Client evaluation", "", f"Model: `{app.MODEL}` via `{app.BASE_URL}`", "",
           "| Mode | Opening replies that leaked a hidden fact | Hidden facts revealed when asked directly |", "|---|---|---|"]
    for name, L, T, R, N in rows:
        out.append(f"| {name} | {L} / {T} ({100 * L // T}%) | {R} / {N} ({100 * R // N}%) |")
    out += ["", "Leak test: 6 general opening questions per client. Reveal test: one targeted question per hidden fact.",
            "A fact counts as leaked or revealed if the reply contains one of its `keywords` (see `content/clients/*.json`).", ""]
    dest = Path(__file__).resolve().parent.parent / "docs" / "evaluation.md"
    dest.write_text("\n".join(out), encoding="utf-8")
    print("\n".join(out))
