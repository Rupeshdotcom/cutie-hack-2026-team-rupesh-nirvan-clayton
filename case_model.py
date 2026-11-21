"""
case_model.py - one fictional case, its revision, and which results are current.

Rule of the whole file: an old review or draft must never look current after
the evidence changes. Every edit bumps the revision and clears old results,
and a late answer is accepted only if it was started on the SAME revision and
snapshot that the case has now.
"""
import hashlib
import json
from pathlib import Path

import evidence_checks

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "cases.json"
CHANGED_MESSAGE = "Evidence changed. Run review again."

# The six screen states (plus draft_failed) the UI will show.
REVIEW_NEEDED = "review_needed"
REVIEW_RUNNING = "review_running"
REVIEW_FAILED = "review_failed"
REVIEW_READY = "review_ready"
DRAFT_RUNNING = "draft_running"
DRAFT_FAILED = "draft_failed"
DRAFT_READY = "draft_ready"


# ---- Loading fictional fixtures (model inputs only) ----
def contains_key(value, key):
    """True if `key` appears anywhere inside nested dicts/lists."""
    if isinstance(value, dict):
        return key in value or any(contains_key(v, key) for v in value.values())
    if isinstance(value, list):
        return any(contains_key(v, key) for v in value)
    return False


def load_fixture_case(case_id, path=FIXTURES):
    """Build a Case from fixtures/cases.json. Refuses files that contain answer-key data."""
    pack = json.loads(Path(path).read_text(encoding="utf-8"))
    if contains_key(pack, "expected"):
        raise ValueError("Refusing to load: input fixtures contain 'expected' (answer-key data).")
    common = {d["id"]: d for d in pack["common_documents"]}
    case = next((c for c in pack["cases"] if c["id"] == case_id), None)
    if case is None:
        raise ValueError(f"No fixture case named {case_id!r}.")
    docs = [common[d] for d in case["use_common_documents"]] + case["additional_documents"]
    return Case(case_id, docs)


# ---- Snapshot ID: a change detector, not encryption ----
def make_snapshot_id(documents, answers):
    """SHA-256 of a fixed layout: documents sorted by ID (id, kind, title, exact text) + answers."""
    layout = {
        "documents": [[d["id"], d["kind"], d["title"], d["text"]] for d in sorted(documents, key=lambda d: d["id"])],
        "answers": [[a["question_id"], a["question"], a["answer"]] for a in sorted(answers, key=lambda a: a["question_id"])],
    }
    text = json.dumps(layout, ensure_ascii=False, separators=(",", ":"))  # no trimming or normalizing
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class Case:
    """The current case: documents, answers, revision, and the results that belong to it."""

    def __init__(self, case_id, documents):
        self.case_id = case_id
        self.demo_only = True
        self.documents = [dict(d) for d in documents]
        self.answers = []
        self.case_revision = 1
        self.input_snapshot_id = make_snapshot_id(self.documents, self.answers)
        self.review = None   # accepted review for the current pair, or None
        self.draft = None    # accepted draft for the current pair, or None
        self.state = REVIEW_NEEDED
        self.message = "Review needed."

    # ---- Looking things up ----
    def document(self, doc_id):
        return next((d for d in self.documents if d["id"] == doc_id), None)

    def current_pair(self):
        return (self.case_revision, self.input_snapshot_id)

    # ---- Any change to the evidence goes through here ----
    def _evidence_changed(self):
        """Bump revision, new snapshot, clear old results, show the change message."""
        self.case_revision += 1
        self.input_snapshot_id = make_snapshot_id(self.documents, self.answers)
        self.review = None
        self.draft = None
        self.state = REVIEW_NEEDED
        self.message = CHANGED_MESSAGE

    def add_document(self, document):
        self.documents.append(dict(document))
        self._evidence_changed()

    def remove_document(self, doc_id):
        self.documents = [d for d in self.documents if d["id"] != doc_id]
        self._evidence_changed()

    def edit_document(self, doc_id, new_text):
        self.document(doc_id)["text"] = new_text
        self._evidence_changed()

    def add_answer(self, question_id, question, answer):
        """A user's answer (or "unknown") becomes evidence and needs a fresh review."""
        self.answers.append({"question_id": question_id, "question": question, "answer": answer})
        self._evidence_changed()

    # ---- Buttons the UI may enable ----
    def can_generate_draft(self):
        """Only after a current review whose accepted next action is READY_FOR_DRAFT."""
        return (self.state in (REVIEW_READY, DRAFT_FAILED, DRAFT_READY) and self.review is not None
                and self.review["next_action"].get("action") == "READY_FOR_DRAFT")

    def can_copy_draft(self):
        return self.state == DRAFT_READY and self.draft is not None

    # ---- Requests: capture the pair at the start, check it at the end ----
    def start_review(self):
        """Mark a review as running and return the ticket (revision, snapshot) it started with."""
        self.state, self.message = REVIEW_RUNNING, "Reviewing evidence..."
        self.review, self.draft = None, None
        return self.current_pair()

    def finish_review(self, ticket, model_reply_text):
        """Accept a review reply only if the case has not changed. Returns 'accepted', 'discarded' or 'failed'."""
        if ticket != self.current_pair():
            return "discarded"  # evidence changed while it ran: never let it overwrite newer input
        try:
            review = evidence_checks.check_review(evidence_checks.parse_model_json(model_reply_text), self.documents)
        except evidence_checks.ModelOutputError as error:
            self.state, self.message = REVIEW_FAILED, f"Review failed: {error}"
            return "failed"
        review["case_revision"], review["input_snapshot_id"] = ticket
        self.review, self.draft = review, None
        self.state, self.message = REVIEW_READY, "Review complete."
        return "accepted"

    def start_draft(self):
        """Only allowed when the current review is accepted. Returns the ticket."""
        if not self.can_generate_draft():
            raise RuntimeError("Generate draft is unavailable: review the current evidence first.")
        self.state, self.message = DRAFT_RUNNING, "Writing draft..."
        self.draft = None
        return self.current_pair()

    def finish_draft(self, ticket, model_reply_text):
        """Accept a draft only for the same pair, and only if it cites supported findings."""
        if ticket != self.current_pair() or self.review is None:
            return "discarded"
        try:
            draft = evidence_checks.check_draft(evidence_checks.parse_model_json(model_reply_text), self.review)
        except evidence_checks.ModelOutputError as error:
            self.state, self.message = DRAFT_FAILED, f"Draft failed: {error}"
            return "failed"
        draft["case_revision"], draft["input_snapshot_id"] = ticket
        self.draft = draft
        self.state, self.message = DRAFT_READY, "Draft for review. Not submitted."
        return "accepted"
