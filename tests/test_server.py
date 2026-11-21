"""
Offline tests for the local website (server.py). Fake model replies and a fake
Solari page, so no network and no API calls. Run with the other tests:
python -m unittest discover -s tests -v
"""
import json
import os
import sys
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import prompts  # noqa: E402
import server  # noqa: E402
from test_offline import FAKE_DRAFT, fake_review  # noqa: E402

PAGE = {"ok": True, "url": prompts.ALLOWED_SOURCES[0], "title": "Internal appeals",
        "text": "You can file an internal appeal.", "checked_at": "2026-11-21T23:00:00Z"}


def retrieval_reply():
    reply = json.loads(fake_review(action="RETRIEVE_PUBLIC_GUIDANCE", related=()))
    reply["next_action"]["source_url"] = prompts.ALLOWED_SOURCES[0]
    return json.dumps(reply)


class Website(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()

    def setUp(self):
        self.replies = []
        self.retrieve_result = PAGE
        server.ASK = lambda *a, **k: self.replies.pop(0)
        server.RETRIEVE = lambda url: self.retrieve_result

    def get(self, path):
        with urllib.request.urlopen(self.base + path) as res:
            return res.read().decode("utf-8")

    def post(self, path, body):
        req = urllib.request.Request(self.base + path, json.dumps(body).encode(), {"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req) as res:
                return res.status, json.loads(res.read())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read())

    def load(self, case_id="evidence-present"):
        return self.post("/api/load", {"case_id": case_id})[1]

    # ---- 1. Case picker ----
    def test_cases_are_labelled_fictional(self):
        cases = json.loads(self.get("/api/cases"))["cases"]
        self.assertEqual(len(cases), 5)
        self.assertTrue(all(c["title"].startswith("FICTIONAL") for c in cases))

    # ---- 2. Edits clear old results ----
    def test_edit_clears_review_and_draft(self):
        self.load()
        self.replies = [fake_review(action="READY_FOR_DRAFT", related=()), FAKE_DRAFT]
        self.post("/api/review", {})
        s = self.post("/api/draft", {"limited": False})[1]
        self.assertTrue(s["can_copy"])
        s = self.post("/api/edit", {"doc_id": "referral-fictional-1", "text": "Edited referral."})[1]
        self.assertEqual(s["message"], "Evidence changed. Run review again.")
        self.assertIsNone(s["review"])
        self.assertIsNone(s["draft"])
        self.assertFalse(s["can_generate_draft"] or s["can_copy"])

    def test_unchanged_text_is_not_an_edit(self):
        s = self.load()
        doc = s["documents"][0]
        s2 = self.post("/api/edit", {"doc_id": doc["id"], "text": doc["text"]})[1]
        self.assertEqual(s2["revision"], s["revision"])

    # ---- 3 + 4. Review, status, findings with source passages ----
    def test_review_shows_action_findings_and_sources(self):
        self.load()
        self.replies = [fake_review(action="READY_FOR_DRAFT", related=())]
        s = self.post("/api/review", {})[1]
        self.assertEqual(s["outcome"]["outcome"], "ready_for_draft")
        f3 = next(f for f in s["review"]["findings"] if f["id"] == "f3")
        self.assertEqual(f3["status"], "supported")
        self.assertEqual(f3["sources"][0]["passage"], "with completion documented")
        self.assertIn("treatment record", f3["sources"][0]["title"])
        self.assertTrue(s["can_generate_draft"])
        self.assertFalse(s["can_request_limited_draft"])

    # ---- 5 + 6. Question, "unknown", STOP, limited draft ----
    def test_question_unknown_then_limited_draft(self):
        self.load()
        self.replies = [fake_review()]
        s = self.post("/api/review", {})[1]
        self.assertTrue(s["question"])
        self.assertFalse(s["can_generate_draft"])
        s = self.post("/api/answer", {"answer": ""})[1]  # blank counts as "unknown"
        self.assertEqual(s["message"], "Evidence changed. Run review again.")
        self.replies = [fake_review(action="STOP_UNRESOLVED", related=())]
        s = self.post("/api/review", {})[1]
        self.assertTrue(s["can_request_limited_draft"])
        self.assertFalse(s["can_generate_draft"])
        self.replies = [FAKE_DRAFT]
        s = self.post("/api/draft", {"limited": True})[1]
        self.assertTrue(s["draft"]["limited"])
        self.assertIn("[PLACEHOLDER:", s["draft"]["text"])
        self.assertTrue(s["draft"]["text"].endswith("Draft for review. Not submitted."))

    def test_disabled_draft_is_refused(self):
        self.load()
        status, body = self.post("/api/draft", {"limited": False})
        self.assertEqual(status, 400)
        self.assertIn("unavailable", body["error"])

    # ---- 7. Public guidance panel ----
    def test_guidance_live_and_unavailable(self):
        self.load()
        self.replies = [retrieval_reply(), fake_review(action="READY_FOR_DRAFT", related=())]
        s = self.post("/api/review", {})[1]
        self.assertEqual(s["guidance"][0]["status"], "live")
        self.assertEqual(s["guidance"][0]["url"], prompts.ALLOWED_SOURCES[0])
        self.assertEqual(s["guidance"][0]["checked_at"], PAGE["checked_at"])

        self.load()
        self.retrieve_result = {"ok": False, "url": prompts.ALLOWED_SOURCES[0], "checked_at": PAGE["checked_at"],
                                "reason": "Browser error: the page took too long to load"}
        self.replies = [retrieval_reply()]
        s = self.post("/api/review", {})[1]
        self.assertEqual(s["guidance"][0]["status"], "unavailable")
        self.assertIn("took too long", s["guidance"][0]["reason"])

    # ---- Keys never reach the browser ----
    def test_no_keys_in_page_or_state(self):
        self.load()
        self.replies = [fake_review(action="READY_FOR_DRAFT", related=())]
        texts = [self.get("/"), self.get("/api/state"), json.dumps(self.post("/api/review", {})[1])]
        secrets = [v for k, v in os.environ.items() if k.endswith("API_KEY") and v]
        for text in texts:
            self.assertNotIn("API_KEY", text)
            for value in secrets:
                self.assertNotIn(value, text)


if __name__ == "__main__":
    unittest.main()
