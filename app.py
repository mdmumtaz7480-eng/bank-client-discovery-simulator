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


def client_reply(client, history, unlocked=None):
    unlocked = unlocked_items(client, history) if unlocked is None else unlocked
    hidden = "\n".join(f"- {h['detail']}" for h in unlocked) or "(nothing unlocked yet: share none of your private matters)"
    sys_prompt = load_prompts()["client_system"].format(
        profile=fmt_profile(client), personality=client["personality"], hidden=hidden
    )
    msgs = [{"role": "system", "content": sys_prompt}]
    for m in history:  # student = "user", client = "assistant"
        msgs.append({"role": "user" if m["role"] == "student" else "assistant", "content": m["content"]})
    return chat_completion(msgs)


_GREETING = re.compile(r"^\s*(hello|hi|hey|good (morning|afternoon|evening)|salam|assalam[^,.!]*)[^,.!?]*[,.!]\s*", re.I)
_OPEN = re.compile(r"^(what|how|why|who|where|when|which|tell me|describe|walk me|explain|talk me|help me understand|in what|could you (tell|describe|explain|share|walk)|can you (tell|describe|explain|share|walk))\b", re.I)
_CLOSED = re.compile(r"^(do|does|did|is|are|was|were|have|has|had|can|could|will|would|should|shall)\b", re.I)


def question_technique(history):
    """Deterministic questioning-technique stats: open (what/how/why/tell me...) vs closed (yes/no) questions."""
    open_q = closed_q = other = 0
    for m in history:
        if m["role"] != "student":
            continue
        text = _GREETING.sub("", m["content"].strip())
        parts = [p.strip() for p in re.split(r"(?<=[.?!])\s+", text) if p.strip()]
        q = next((p for p in reversed(parts) if "?" in p), parts[-1] if parts else "")
        if _OPEN.match(q):
            open_q += 1
        elif _CLOSED.match(q):
            closed_q += 1
        else:
            other += 1
    return {"open": open_q, "closed": closed_q, "other": other, "total": open_q + closed_q + other}


def discovery_report(client, history):
    """Which hidden needs did the student uncover, and with which question? (first unlocking question wins)"""
    found = {}
    for m in history:
        if m["role"] == "student":
            for n in _topics_for_question(client, m["content"]):
                found.setdefault(n, m["content"])
    return [
        {"topic": h["topic"], "importance": h.get("importance", "medium"), "found": (i + 1) in found,
         "question": found.get(i + 1)}
        for i, h in enumerate(client["hidden_information"])
    ]


def product_verdicts(client, recommendations, products):
    text = recommendations.lower()
    out = []
    for p in products:
        if p["name"].split(" (")[0].lower() in text or p["id"] in text:
            v = "suitable" if p["id"] in client.get("suitable_product_ids", []) else (
                "unsuitable" if p["id"] in client.get("unsuitable_product_ids", []) else "debatable")
            out.append({"id": p["id"], "name": p["name"].split(" (")[0], "verdict": v})
    return out


def fmt_transcript(client, history):
    return "\n".join(
        f"{'STUDENT' if m['role'] == 'student' else client['name'].upper()}: {m['content']}" for m in history
    )


def coverage_check(client, history):
    """Ground truth for the coach: a hidden fact counts as REVEALED when the student's questions unlocked it."""
    unlocked = {h["topic"] for h in unlocked_items(client, history)}
    return "\n".join(
        f"- {h['topic']}: {'REVEALED to the student' if h['topic'] in unlocked else 'NOT REVEALED (the student never asked about it)'}"
        for h in client["hidden_information"]
    )


def product_check(client, recommendations, products):
    """Which catalogue products did the student recommend, and are they suitable for this client?"""
    text = recommendations.lower()
    lines = []
    for p in products:
        if p["name"].split(" (")[0].lower() in text or p["id"] in text:
            ok = p["id"] in client.get("suitable_product_ids", [])
            bad = p["id"] in client.get("unsuitable_product_ids", [])
            verdict = "SUITABLE" if ok else ("UNSUITABLE for this client" if bad else "debatable")
            lines.append(f"- {p['name']}: {verdict}. Limitations: {'; '.join(p['limitations'])}")
    return "\n".join(lines) or "- (no catalogue product recognised in the recommendations)"


def unsuitable_warnings(client, recommendations, products):
    text = recommendations.lower()
    by_id = {p["id"]: p for p in products}
    better = ", ".join(by_id[i]["name"] for i in client.get("suitable_product_ids", []) if i in by_id)
    out = []
    for p in products:
        if p["id"] in client.get("unsuitable_product_ids", []) and (p["name"].split(" (")[0].lower() in text or p["id"] in text):
            out.append(f"- **Unsuitable recommendation: {p['name']}**. Limitations: {'; '.join(p['limitations'])}. "
                       f"These conflict with {client['name'].split()[0]}'s situation (see the needs above)."
                       + (f" Better fit from the catalogue: {better}." if better else ""))
    return out


def coach_feedback(client, history, summary, recommendations, products):
    transcript = fmt_transcript(client, history)
    coverage = coverage_check(client, history)
    product_verdicts = product_check(client, recommendations, products)
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
        f"CHECK OF THE STUDENT'S RECOMMENDED PRODUCTS (verified)\n{product_verdicts}\n\n"
        f"PRODUCT CATALOGUE\n{catalogue}\n\nINTERVIEW TRANSCRIPT\n{transcript}\n\n"
        f"STUDENT'S SUMMARY OF CLIENT NEEDS\n{summary}\n\nSTUDENT'S PRODUCT RECOMMENDATIONS\n{recommendations}\n\n"
        "Now write your coaching feedback."
    )
    fb = chat_completion(
        [{"role": "system", "content": load_prompts()["coach_system"]}, {"role": "user", "content": user}],
        temperature=0.4,
    )
    warnings = unsuitable_warnings(client, recommendations, products)
    if warnings and "## How to improve" in fb:  # guaranteed, not left to the small model
        head, tail = fb.split("## How to improve", 1)
        fb = head.rstrip() + "\n" + "\n".join(warnings) + "\n\n## How to improve" + tail
    return fb


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
                 "profile": c["public_profile"], "hidden_count": len(c["hidden_information"])}
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
                unlocked = unlocked_items(client, history)
                found = [{"topic": h["topic"], "importance": h.get("importance", "medium")} for h in unlocked]
                return self._send(200, {"reply": client_reply(client, history, unlocked), "discovered": found,
                                        "total": len(client["hidden_information"])})
            if self.path == "/api/feedback":
                products = load_products()
                summary = body.get("summary", "").strip() or "(none provided)"
                recs = body.get("recommendations", "").strip() or "(none provided)"
                fb = coach_feedback(client, history, summary, recs, products)
                return self._send(200, {"feedback": fb, "insights": {
                    "discovery": discovery_report(client, history),
                    "technique": question_technique(history),
                    "products": product_verdicts(client, recs, products)}})
            self._send(404, {"error": "not found"})
        except Exception as e:  # prototype: surface errors to the UI
            self._send(502, {"error": str(e)})

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    print(f"Bank Client Discovery Simulator -> http://localhost:{PORT}\nModel: {MODEL} @ {BASE_URL}")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
