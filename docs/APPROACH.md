# Approach and design decisions

## The problem
Students need to practise *discovery*: asking questions that draw out what a client has not said, then matching products to
real needs. An AI Client must therefore (a) stay in character, (b) hold back private facts until asked, and (c) react
realistically to product proposals. An AI Coach must (d) judge the student against ground truth, not its own guess.

## What I built
```
student question ─► unlock classifier ─► client prompt (only unlocked facts) ─► in-character reply
transcript + summary + recommendations ─► deterministic checks ─► AI Coach ─► feedback
```

| Decision | Why | Alternative rejected |
|---|---|---|
| **Unlock classifier gates hidden facts** | A locked fact that is not in the prompt cannot leak. Instructions like "do not reveal X" are only requests to the model. | One big prompt with all facts and rules |
| **Coverage and product checks computed in code** | A 7B model told a student they "missed" something the client had just said. Ground truth should not be left to the model. | Asking the coach to work it out from the transcript |
| **Unsuitable-product warnings injected by code** | The coach ignored a verdict I gave it. The most important lesson must be guaranteed. | Stronger wording in the prompt |
| **Stdlib Python + plain HTML/JS** | Runs with no installs, easy to review, focus stays on the AI logic. | Framework, vector DB, agent library |
| **Content in JSON files** | Educators can add clients and products without code. | Hard-coded personas |
| **OpenAI-compatible API only** | Works with local models and hosted providers by changing `.env`. | Provider SDK |
| **No score, a discovery map instead** | The brief asks for learning, not grading. The map shows which question uncovered which need. | A 0-100 score |

## Problems I hit, and what I did
1. **Client leaked on openings.** Prompt-only, Fatima volunteered late payments in 2 of 6 openings. Rule-tightening did not remove it, so I changed the architecture to gate facts (see above).
2. **Classifier confused by long history.** Given all questions at once it mis-unlocked. Fixed by classifying each question separately and caching.
3. **Coach contradicted the transcript.** Fixed with the code-computed coverage checklist.
4. **Coach skipped unsuitable products.** Fixed by injecting the warnings in code.

## Evidence
`tests/` (13 offline tests) proves the leak barrier with the model stubbed. `scripts/evaluate.py` measured the model:
0 of 12 openings leaked when gated vs 1 of 12 prompt-only; 6 of 11 vs 7 of 11 facts revealed when asked directly (strict
keyword scoring undercounts; see `docs/evaluation.md`). One trial per question on a 7B local model, so a starting point, not a benchmark.

## Known limitations
- Small local model: coaching prose can nitpick and small role-play slips happen. A larger model through the same `.env` helps.
- The unlock classifier can miss a low-priority fact (e.g. "Who are your customers?" did not unlock "customers are corporates").
- Open/closed question detection is rule-based and English-only.
- Evaluation is small, single-trial and keyword-scored.
- No authentication or persistence; prototype only.

## What I would do next
1. **Better evaluation:** several trials per question, more probes, and an LLM judge for "was this fact stated".
2. **Streaming replies** so the client types in real time (latency was the main UX cost on a local model).
3. **More personas and difficulty levels** (a client who lies, a hostile client, a client with contradictory goals).
4. **Instructor view:** class-level view of which needs students most often miss.
5. **Arabic support** for client and coach, relevant to Qatar.
6. **Rubric alignment** with the programme's own interview rubric, so feedback maps to course outcomes.
