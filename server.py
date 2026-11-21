"""
server.py - the local demo website (Python's built-in http.server, no extra packages).

Start:  python server.py      then open http://127.0.0.1:8000
The page only talks to this Python server. All Gemini and Solari calls happen
here, so API keys never reach the browser. One fictional case at a time.
"""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import agent
from case_model import FIXTURES, load_fixture_case
from llm import ask_gemini
from public_sources import retrieve_public_page

ROOT = Path(__file__).resolve().parent
PAGE = ROOT / "static" / "index.html"
HOST, PORT = "127.0.0.1", 8000
EDITABLE_KINDS = ("denial", "policy_excerpt", "case_fact", "user_report")

# Swappable so tests can use fake replies instead of real API calls.
ASK = ask_gemini
RETRIEVE = retrieve_public_page

case = None  # the one case on screen


# ---- What the page needs to draw itself ----
def current_outcome():
    return case.budgets.get(case.case_revision, {}).get("outcome") if hasattr(case, "budgets") else None


def guidance_panel(outcome):
    """The retrieved public source (URL + time), or the honest unavailable state."""
    pages = [d for d in case.documents if d["kind"] == "public_guidance"]
    if pages:
        return [{"status": "live", "title": d["title"], "url": d["url"], "checked_at": d["checked_at"]} for d in pages]
    if outcome and outcome["reason"].startswith("public guidance unavailable"):
        return [{"status": "unavailable", "url": outcome.get("source_url"), "checked_at": outcome.get("checked_at"),
                 "reason": outcome["reason"]}]
    return []


def state():
    if case is None:
        return {"loaded": False}
    outcome = current_outcome()
    review = None
    if case.review:
        review = {
            "denial_reason": case.review.get("denial_reason"),
            "findings": [{"id": f["id"], "statement": f["statement"], "status": f["status"],
                          "user_reported": f.get("user_reported", False),
                          "downgraded_from": f.get("downgraded_from"),
                          "sources": agent.source_panel(case, f)} for f in case.review["findings"]],
            "limitations": case.review.get("limitations", []),
        }
    return {
        "loaded": True,
        "case_id": case.case_id,
        "revision": case.case_revision,
        "state": case.state,
        "message": case.message,
        "documents": [{k: d.get(k) for k in ("id", "kind", "title", "text")} | {"editable": d["kind"] in EDITABLE_KINDS}
                      for d in case.documents],
        "outcome": outcome,
        "question": outcome["question"] if outcome and outcome["outcome"] == agent.WAITING_FOR_ANSWER else None,
        "review": review,
        "can_generate_draft": case.can_generate_draft(),
        "can_request_limited_draft": case.can_request_limited_draft(),
        "can_copy": case.can_copy_draft(),
        "draft": {"text": case.draft["draft_text"], "limited": case.draft.get("limited", False)} if case.draft else None,
        "guidance": guidance_panel(outcome),
    }


# ---- Actions the page can ask for ----
def list_cases():
    cases = json.loads(FIXTURES.read_text(encoding="utf-8"))["cases"]
    return {"cases": [{"id": c["id"], "title": f"FICTIONAL: {c['title']}"} for c in cases]}


def load(body):
    global case
    case = load_fixture_case(body["case_id"])
    return state()


def edit(body):
    doc = case.document(body["doc_id"])
    if doc is None or doc["kind"] not in EDITABLE_KINDS:
        raise ValueError("That document cannot be edited.")
    if doc["text"] != body["text"]:
        case.edit_document(body["doc_id"], body["text"])
    return state()


def review(_body):
    agent.run_review(case, ask=ASK, retrieve=RETRIEVE, log=lambda _: None)
    return state()


def answer(body):
    outcome = current_outcome()
    if not outcome or outcome["outcome"] != agent.WAITING_FOR_ANSWER:
        raise ValueError("There is no open question.")
    text = (body.get("answer") or "").strip() or "unknown"
    case.add_answer(f"q{len(case.answers) + 1}", outcome["question"], text)
    return state()


def draft(body):
    agent.generate_draft(case, ask=ASK, limited=bool(body.get("limited")))
    return state()


ROUTES = {"/api/load": load, "/api/edit": edit, "/api/review": review, "/api/answer": answer, "/api/draft": draft}


class Handler(BaseHTTPRequestHandler):
    def send_json(self, status, data):
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        if self.path == "/":
            payload = PAGE.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        elif self.path == "/api/cases":
            self.send_json(200, list_cases())
        elif self.path == "/api/state":
            self.send_json(200, state())
        else:
            self.send_json(404, {"error": "Not found."})

    def do_POST(self):
        action = ROUTES.get(self.path)
        if action is None:
            return self.send_json(404, {"error": "Not found."})
        if self.path != "/api/load" and case is None:
            return self.send_json(400, {"error": "Load a fictional case first."})
        length = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
            self.send_json(200, action(body))
        except (ValueError, KeyError, RuntimeError) as error:  # bad request or a disabled action
            self.send_json(400, {"error": str(error)})
        except Exception as error:  # never send raw details to the page
            self.send_json(500, {"error": f"Server error ({type(error).__name__})."})

    def log_message(self, *args):
        pass  # keep the terminal quiet; nothing sensitive is logged


def main():
    print(f"Fictional demo running at http://{HOST}:{PORT}  (Ctrl+C to stop)")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
