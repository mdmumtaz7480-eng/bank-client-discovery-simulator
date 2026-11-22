"""Replays a scripted student interview through the real app logic and saves the
AI Client replies + AI Coach feedback to samples/sample-interview.md.
Run:  python3 scripts/generate_sample.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import app  # noqa: E402

CLIENT_ID = "fatima"
QUESTIONS = [
    "Hello Fatima, thanks for coming in. Can you tell me a bit about yourself and your business?",
    "How is the business doing financially at the moment?",
    "Tell me about your cash flow. Are there times of the month when money is tight?",
    "Who are your customers, and how quickly do they pay you?",
    "What are your plans for the next year or two?",
    "Do you have any preferences about the type of banking you use, for example Sharia-compliant products?",
    "Is there anything else you would like to tell me about your goals?",
]
SUMMARY = ("Fatima runs a catering company with 12 staff and about QAR 220k monthly sales. Her corporate customers pay "
           "after 60-90 days while she pays suppliers in 30, so cash is tight. She wants a second van and a bigger kitchen "
           "and prefers Sharia-compliant banking.")
RECS = ("1) Business Murabaha Finance for the van and kitchen, because it is Sharia-compliant. "
        "2) Invoice Finance to fix the late payments, because it gives her cash within 48 hours. "
        "3) Business Working Capital Line as a back-up for day-to-day cash flow.")

client = app.load_clients()[CLIENT_ID]
history, out = [], [f"# Sample interview: {client['name']}\n",
                    f"_Model: `{app.MODEL}` via `{app.BASE_URL}`_\n", "## 1. Conversation\n"]
for q in QUESTIONS:
    history.append({"role": "student", "content": q})
    a = app.client_reply(client, history)
    history.append({"role": "client", "content": a})
    out.append(f"**Student:** {q}\n\n**{client['name'].split()[0]}:** {a}\n")
out += ["## 2. Student summary and product recommendations\n", f"**Summary:** {SUMMARY}\n", f"**Recommendations:** {RECS}\n"]
fb = app.coach_feedback(client, history, SUMMARY, RECS, app.load_products())
out += ["## 3. AI Coach feedback\n", fb, ""]
dest = Path(__file__).resolve().parent.parent / "samples" / "sample-interview.md"
dest.write_text("\n".join(out), encoding="utf-8")
print("Saved", dest)
