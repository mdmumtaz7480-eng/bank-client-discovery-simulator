# Client evaluation

Model: `qwen2.5:7b` via `http://localhost:11434/v1`

| Mode | Opening replies that leaked a hidden fact | Hidden facts revealed when asked directly |
|---|---|---|
| Gated (this app) | 0 / 12 (0%) | 6 / 11 (54%) |
| Prompt-only baseline | 1 / 12 (8%) | 7 / 11 (63%) |

Leak test: 6 general opening questions per client. Reveal test: one targeted question per hidden fact.
A fact counts as leaked or revealed if the reply contains one of its `keywords` (see `content/clients/*.json`).

## Reading the results honestly

Run on `qwen2.5:7b`, one trial per question (small sample; local model sampling makes single runs noisy).

- **Leaks:** the gated client leaked in 0 of 12 openings, the prompt-only baseline in 1 of 12 (Fatima volunteered her late-paying
  customers on "How can I help you?"). The gap is small on this sample. The real benefit is structural: a locked fact is not in
  the prompt at all, which `tests/test_logic.py` proves without a model.
- **Reveals:** keyword matching undercounts. Diagnosing the 5 gated misses afterwards: in 4 the unlock classifier was right and
  the client stated the fact in different words (for example "education ... overseas" for the university fund, "open ... hidden
  costs" for banking preferences) or the keywords hit on a re-run. One was a genuine classifier miss: "Who are your customers?"
  did not unlock the low-priority "customers are corporates" fact. `reveal_keywords` were widened for future runs.
- **Next step:** several trials per question and a larger probe set, then an LLM-as-judge for "was this fact stated".
