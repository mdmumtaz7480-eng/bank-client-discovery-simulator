# Bank Client Discovery Simulator

A small web app where a student interviews a fictional bank client (**AI Client**), recommends products from a
catalogue, and then receives learning-focused feedback from an **AI Coach**.

Flow: **Select client → Interview → Recommend → Coaching feedback**

- Python 3.9+ standard library only. **No `pip install` needed.**
- Both chatbots call any **OpenAI-compatible** `/chat/completions` API (Ollama, LM Studio, Groq, OpenRouter, OpenAI...).
- No login, no database.

## Run it

```bash
cp .env.example .env      # then edit .env (see below)
python3 app.py
```
Open http://localhost:8000

## Configure the AI connection (`.env`)

| Variable | Meaning | Example |
|---|---|---|
| `AI_BASE_URL` | OpenAI-compatible base URL (ending in `/v1`) | `http://localhost:11434/v1` |
| `AI_API_KEY` | API key (any text for local models) | `ollama` |
| `AI_MODEL` | Model name | `qwen2.5:7b` |
| `AI_TEMPERATURE` | Optional, client temperature | `0.7` |
| `PORT` | Optional web port | `8000` |

Free local option with Ollama: `ollama pull qwen2.5:7b` (Ollama exposes an OpenAI-compatible API at `http://localhost:11434/v1`).
Free hosted options: Groq or OpenRouter free tiers (see `.env.example`). Real environment variables override `.env`.

**AI provider / model used for testing:** **Ollama running `qwen2.5:7b`** (free, open-source, local) through its OpenAI-compatible endpoint `http://localhost:11434/v1`. The committed sample in `samples/sample-interview.md` was generated with it.

## Editing the content (no code changes)

| File | Purpose |
|---|---|
| `content/clients/*.json` | One file per client: public profile, **hidden information**, ideal needs, suitable/unsuitable products. Add a file to add a client. |
| `content/products.json` | Product catalogue (features and limitations). |
| `content/prompts.json` | The AI Client and AI Coach instructions. |

Files are re-read on every request, so edits apply on the next page action.

## How the AI is used

- **AI Client** – a small classifier step first decides which hidden facts the student's questions have *unlocked*; only those facts are put in the client's prompt, so a small model cannot leak the rest. The prompt also has the character, personality and strict rules: answer only
  what is asked, reveal a hidden item only when a relevant question is asked, react in character to product proposals
  and object if a product conflicts with their values or finances. Hidden facts are never sent to the browser.
- **AI Coach** – runs in two steps: (1) a coverage check marks which hidden facts the client actually revealed, then (2) the feedback call uses that checklist so a small model does not call revealed facts "missed". It receives the full client file, the product limitations, the transcript and the student's own summary and
  recommendations, and must answer under *What went well / What was missed / How to improve* with no numeric score.

## Sample interview

Generate one with your configured model (writes `samples/sample-interview.md`):
```bash
python3 scripts/generate_sample.py
```
