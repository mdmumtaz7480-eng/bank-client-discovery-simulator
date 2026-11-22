"""Bank Client Discovery Simulator - tiny stdlib-only web app.

Two AI roles (Client + Coach) share one OpenAI-compatible endpoint configured in .env.
Hidden client information never leaves the server until the coach needs it.
"""
import json
import os
import re
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).parent
CONTENT = ROOT / "content"
STATIC = ROOT / "static"


def load_env(path=ROOT / ".env"):
    """Minimal .env loader (no dependencies). Real environment variables win."""
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


load_env()
BASE_URL = os.environ.get("AI_BASE_URL", "http://localhost:11434/v1").rstrip("/")
API_KEY = os.environ.get("AI_API_KEY", "none")
MODEL = os.environ.get("AI_MODEL", "qwen2.5:7b")
TEMPERATURE = float(os.environ.get("AI_TEMPERATURE", "0.7"))
PORT = int(os.environ.get("PORT", "8000"))


# ---------- content (re-read on every request so files are editable live) ----------
def load_clients():
    clients = {}
    for p in sorted((CONTENT / "clients").glob("*.json")):
        c = json.loads(p.read_text(encoding="utf-8"))
        clients[c["id"]] = c
    return clients


def load_products():
    return json.loads((CONTENT / "products.json").read_text(encoding="utf-8"))


def load_prompts():
    return json.loads((CONTENT / "prompts.json").read_text(encoding="utf-8"))


# ---------- AI call ----------
def chat_completion(messages, temperature=TEMPERATURE):
    body = json.dumps({"model": MODEL, "messages": messages, "temperature": temperature}).encode()
    req = urllib.request.Request(
        f"{BASE_URL}/chat/completions",
        data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            data = json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"AI API error {e.code}: {e.read().decode(errors='replace')[:300]}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Cannot reach AI API at {BASE_URL}: {e.reason}")
    return data["choices"][0]["message"]["content"].strip()


def fmt_profile(c):
    p = c["public_profile"]
    return (
        f"Name: {c['name']}\nAge: {p['age']}\nLocation: {p['location']}\nOccupation: {p['occupation']}\n"
        f"Background: {p['background']}\nFinancial situation: {p['financial_situation']}\n"
        f"Stated need at start: {p['stated_need_at_start']}"
    )


def fmt_hidden(c):
    return "\n".join(f"- [{h['topic']}] {h['detail']}" for h in c["hidden_information"])


_unlock_cache = {}


def _topics_for_question(client, question):
    key = (client["id"], question)
    if key in _unlock_cache:
        return _unlock_cache[key]
    items = client["hidden_information"]
    topics = "\n".join(f"{i + 1}. {h['topic']}" for i, h in enumerate(items))
    prompt = (
        "A banker is interviewing a client. Below are topics the client could talk about, and ONE thing the banker said. "
        "A topic is UNLOCKED only if the banker's message asks about it directly or closely related to it, or proposes a "
        "product whose features or limitations touch it (e.g. interest-based, personal guarantee, fees, lock-in). "
        "Greetings and general questions ('what brings you here', 'tell me about yourself', 'how is business') unlock "
        "nothing. Reply with only the numbers of unlocked topics separated by commas, or NONE.\n\n"
        f"TOPICS\n{topics}\n\nBANKER SAID\n{question}"
    )
    out = chat_completion([{"role": "user", "content": prompt}], temperature=0)
    nums = [int(n) for n in re.findall(r"\d+", out) if 0 < int(n) <= len(items)]
    _unlock_cache[key] = nums
    return nums


def unlocked_items(client, history):
    """Structural guard against leaks: a cheap AI step decides, per student message, which hidden facts it
    'unlocks'. Only unlocked facts are ever put in the client's prompt, so the model cannot leak the rest."""
    items = client["hidden_information"]
    nums = {n for m in history if m["role"] == "student" for n in _topics_for_question(client, m["content"])}
    return [items[n - 1] for n in sorted(nums)]


def client_reply(client, history):
    unlocked = unlocked_items(client, history)
    hidden = "\n".join(f"- {h['detail']}" for h in unlocked) or "(nothing unlocked yet: share none of your private matters)"
    sys_prompt = load_prompts()["client_system"].format(
        profile=fmt_profile(client), personality=client["personality"], hidden=hidden
    )
    msgs = [{"role": "system", "content": sys_prompt}]
    for m in history:  # student = "user", client = "assistant"
        msgs.append({"role": "user" if m["role"] == "student" else "assistant", "content": m["content"]})
    return chat_completion(msgs)


def fmt_transcript(client, history):
    return "\n".join(
        f"{'STUDENT' if m['role'] == 'student' else client['name'].upper()}: {m['content']}" for m in history
    )


def coverage_check(client, history):
    """AI step 1 of coaching: for each hidden item, did the CLIENT reveal it in the transcript?
    Small models lose track of long transcripts, so the coach gets this checklist as ground truth."""
    items = "\n".join(f"{i + 1}. {h['topic']}: {h['detail']}" for i, h in enumerate(client["hidden_information"]))
    prompt = (
        "Below is an interview transcript and a numbered list of hidden facts about the client. For EACH fact decide "
        "whether the client actually revealed it in the transcript (the client's own words state it). "
        "Answer one line per fact in exactly this format:\n"
        "<number>. <topic> - REVEALED (<the student question that drew it out>) or NOT REVEALED\n\n"
        f"HIDDEN FACTS\n{items}\n\nTRANSCRIPT\n{fmt_transcript(client, history)}"
    )
    return chat_completion([{"role": "user", "content": prompt}], temperature=0)


def coach_feedback(client, history, summary, recommendations, products):
    transcript = fmt_transcript(client, history)
    coverage = coverage_check(client, history)
    by_id = {p["id"]: p for p in products}
    catalogue = "\n".join(
        f"- {p['name']} (Sharia-compliant: {p['sharia_compliant']}): features: {'; '.join(p['features'])}. "
        f"Limitations: {'; '.join(p['limitations'])}"
        for p in products
    )
    suitable = ", ".join(by_id[i]["name"] for i in client.get("suitable_product_ids", []) if i in by_id)
    unsuitable = ", ".join(by_id[i]["name"] for i in client.get("unsuitable_product_ids", []) if i in by_id)
    user = (
        f"CLIENT FILE\n{fmt_profile(client)}\n\nHIDDEN INFORMATION THE STUDENT SHOULD HAVE UNCOVERED\n{fmt_hidden(client)}\n\n"
        f"IDEAL NEEDS AND PRODUCT FIT\n{client['ideal_needs_summary']}\nSuitable: {suitable}\nUnsuitable: {unsuitable}\n\n"
        f"COVERAGE CHECKLIST (verified; trust this over your own reading of the transcript)\n{coverage}\n\n"
        f"PRODUCT CATALOGUE\n{catalogue}\n\nINTERVIEW TRANSCRIPT\n{transcript}\n\n"
        f"STUDENT'S SUMMARY OF CLIENT NEEDS\n{summary}\n\nSTUDENT'S PRODUCT RECOMMENDATIONS\n{recommendations}\n\n"
        "Now write your coaching feedback."
    )
    return chat_completion(
        [{"role": "system", "content": load_prompts()["coach_system"]}, {"role": "user", "content": user}],
        temperature=0.4,
    )


# ---------- HTTP ----------
class Handler(BaseHTTPRequestHandler):
    def _send(self, code, payload, ctype="application/json"):
        data = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/api/clients":  # public info only - hidden needs stay on the server
            out = [
                {"id": c["id"], "name": c["name"], "tagline": c["tagline"], "avatar": c["avatar"],
                 "profile": c["public_profile"]}
                for c in load_clients().values()
            ]
            return self._send(200, out)
        if path == "/api/products":
            return self._send(200, load_products())
        if path == "/api/config":
            return self._send(200, {"model": MODEL, "base_url": BASE_URL})
        name = "index.html" if path == "/" else path.lstrip("/")
        f = (STATIC / name).resolve()
        if STATIC.resolve() in f.parents and f.is_file():
            ctype = {".html": "text/html", ".js": "text/javascript", ".css": "text/css"}.get(f.suffix, "text/plain")
            return self._send(200, f.read_bytes(), ctype + "; charset=utf-8")
        self._send(404, {"error": "not found"})

    def do_POST(self):
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            clients = load_clients()
            client = clients.get(body.get("client_id"))
            if not client:
                return self._send(400, {"error": "unknown client"})
            history = body.get("messages", [])
            if self.path == "/api/chat":
                return self._send(200, {"reply": client_reply(client, history)})
            if self.path == "/api/feedback":
                fb = coach_feedback(client, history, body.get("summary", "").strip() or "(none provided)",
                                    body.get("recommendations", "").strip() or "(none provided)", load_products())
                return self._send(200, {"feedback": fb})
            self._send(404, {"error": "not found"})
        except Exception as e:  # prototype: surface errors to the UI
            self._send(502, {"error": str(e)})

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    print(f"Bank Client Discovery Simulator -> http://localhost:{PORT}\nModel: {MODEL} @ {BASE_URL}")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
