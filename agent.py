"""
agent.py - the bounded controller (Pack v2 section C).

Each review cycle, Gemini proposes exactly ONE next action. Code validates it:
  ASK_USER                 -> pause with one new question (never a repeat)
  RETRIEVE_PUBLIC_GUIDANCE -> allowlisted URL only; read live with Solari, added as evidence,
                              then reviewed again in the SAME run (budget is not renewed)
  READY_FOR_DRAFT          -> Generate draft becomes available (user still decides)
  STOP_UNRESOLVED          -> stop, keep what is missing visible, no auto-retry;
                              the user may deliberately request a LIMITED draft
Limits per case revision: MAX_CYCLES review calls, MAX_RETRIEVALS lookups.
"""
import json
import re
from pathlib import Path

import case_model
import prompts
from llm import LLMError, ask_gemini
from public_sources import retrieve_public_page

MAX_CYCLES = 3
MAX_RETRIEVALS = 2
DRAFT_LABEL = "Draft for review. Not submitted."
LIMITED_LABEL = "LIMITED DRAFT - some facts are unresolved."
REVIEWS_DIR = Path(__file__).resolve().parent / "outputs" / "reviews"

# Outcomes a run can end in (shown to the user with a reason).
WAITING_FOR_ANSWER = "waiting_for_answer"
READY = "ready_for_draft"
UNRESOLVED = "stopped_unresolved"
FAILED = "review_failed"
DISCARDED = "discarded"

def budget_for(case):
    """One budget per case revision, stored on the case. A new revision (an edit or answer)
    gets a fresh one; evidence retrieved inside a run does NOT renew it."""
    if not hasattr(case, "budgets"):
        case.budgets = {}
    return case.budgets.setdefault(case.case_revision,
                                   {"cycles": 0, "retrievals": 0, "urls": [], "outcome": None})


def normalize(question):
    """Lowercase, letters and digits only, so tiny wording changes still count as a repeat."""
    return re.sub(r"[^a-z0-9]+", " ", (question or "").lower()).strip()


def asked_questions(case):
    """Every question already asked or answered for this case (all revisions)."""
    return [a["question"] for a in case.answers] + list(getattr(case, "asked_questions", []))


def finish(case, budget, outcome, reason, **extra):
    """Record and return how the run ended (also printed by main.py)."""
    budget["outcome"] = dict({"outcome": outcome, "reason": reason, "cycles_used": budget["cycles"],
                              "retrievals_used": budget["retrievals"]}, **extra)
    return budget["outcome"]


# ---- Code checks on the model's proposed action ----
def check_action(case, budget, action):
    """Return None if the proposal is acceptable, else feedback for the next cycle."""
    kind = action.get("action")
    if kind == "ASK_USER":
        question = (action.get("question") or "").strip()
        if not question:
            return "ASK_USER needs one question."
        if question.count("?") > 1:
            return f"Ask for exactly one fact in one question, not several: {question}"
        tokens = normalize(question).split()
        qwords = {"what", "when", "where", "who", "why", "how", "did", "does", "was",
                "were", "is", "are", "can", "could", "which"}
        if sum(t in qwords for t in tokens) >= 2 and (" and " in normalize(question) or "," in question):
            return f"Ask for exactly one fact in one question, not several: {question}"

        if normalize(question) in {normalize(q) for q in asked_questions(case)}:
            return f"Question already asked or answered, do not repeat it: {question}"
    if kind == "RETRIEVE_PUBLIC_GUIDANCE":
        url = action.get("source_url")
        if url not in prompts.ALLOWED_SOURCES:
            return f"URL is not on the allowed list: {url}"
        if url in budget["urls"]:
            return f"URL already used in this run: {url}"
        if budget["retrievals"] >= MAX_RETRIEVALS:
            return "Retrieval budget is used up; choose another action."
    return None


# ---- One bounded run for the current revision ----
def add_guidance(case, page):
    """Add a retrieved public page to the case as evidence, with its real URL and time."""
    number = sum(d["kind"] == "public_guidance" for d in case.documents) + 1
    case.add_document({
        "id": f"guidance-{number}",
        "kind": "public_guidance",
        "title": f"Public process guidance (live, checked {page['checked_at']}): {page['title']}",
        "text": page["text"],
        "url": page["url"],
        "checked_at": page["checked_at"],
        "live": True,
    })


def run_review(case, ask=ask_gemini, log=print, retrieve=retrieve_public_page):
    """Review cycles until a valid action ends the run or the budget is reached."""
    budget = budget_for(case)
    if budget["outcome"] and budget["outcome"]["outcome"] != FAILED:
        return budget["outcome"]  # this revision already finished; only a failed run may be retried
    if budget["cycles"] >= MAX_CYCLES:
        return finish(case, budget, UNRESOLVED, f"cycle budget of {MAX_CYCLES} reached")
    notes = []
    while budget["cycles"] < MAX_CYCLES:
        budget["cycles"] += 1
        previous = current_review(case)  # kept if this cycle fails
        ticket = case.start_review()
        try:
            reply = ask(prompts.review_input(case, asked_questions(case), notes),
                        instructions=prompts.REVIEW_INSTRUCTIONS, json_mode=True)
        except LLMError as error:  # error text is already a fixed, safe sentence
            case.state, case.message = case_model.REVIEW_FAILED, f"Review failed: {error}"
            case.review = previous
            return finish(case, budget, FAILED, str(error))
        result = case.finish_review(ticket, reply)
        if result == "discarded":
            return {"outcome": DISCARDED, "reason": "evidence changed while the review ran"}
        if result == "failed":
            case.review = previous
            return finish(case, budget, FAILED, case.message)  # no automatic retry
        save_review_file(case)  # saved immediately, so a later failure cannot lose it

        action = case.review["next_action"]
        problem = check_action(case, budget, action)
        log(f"Cycle {budget['cycles']}: model proposed {action['action']} ({action.get('reason', '')})"
            + (f" -> rejected by code: {problem}" if problem else ""))
        if problem:
            notes.append(problem)
            continue

        kind = action["action"]
        if kind == "ASK_USER":
            case.asked_questions = getattr(case, "asked_questions", []) + [action["question"]]
            return finish(case, budget, WAITING_FOR_ANSWER, action.get("reason", ""), question=action["question"])
        if kind == "RETRIEVE_PUBLIC_GUIDANCE":
            url = action["source_url"]
            budget["urls"].append(url)
            budget["retrievals"] += 1
            page = retrieve(url)
            if not page["ok"]:
                log(f"Retrieval of {url} unavailable: {page['reason']}")
                return finish(case, budget, UNRESOLVED, f"public guidance unavailable: {page['reason']}",
                              source_url=url, checked_at=page["checked_at"])
            log(f"Retrieved {page['url']} at {page['checked_at']}; reviewing again with it")
            add_guidance(case, page)  # new revision clears old findings...
            case.budgets[case.case_revision] = budget  # ...but the run keeps its budget
            continue
        if kind == "READY_FOR_DRAFT":
            return finish(case, budget, READY, action.get("reason", ""))
        return finish(case, budget, UNRESOLVED, action.get("reason", ""))

    return finish(case, budget, UNRESOLVED, f"cycle budget of {MAX_CYCLES} reached ({'; '.join(notes)})")


# ---- Draft: only on the user's request ----
def unresolved_placeholders(review):
    """One visible placeholder per finding that is NOT supported (built by code, not the model)."""
    return [f"[PLACEHOLDER: unresolved ({f['status']}) - {f['statement']}]"
            for f in review["findings"] if f["status"] != "supported"]


def finalize_text(text, review, limited):
    """Limited drafts get the label at the top and every unresolved item listed; all end with DRAFT_LABEL."""
    body = text.strip()
    if body.endswith(DRAFT_LABEL):
        body = body[: -len(DRAFT_LABEL)].rstrip()
    if limited:
        if not body.startswith(LIMITED_LABEL):
            body = LIMITED_LABEL + "\n\n" + body
        body += "\n\nUnresolved items (not asserted):\n" + "\n".join(unresolved_placeholders(review))
    return body + "\n\n" + DRAFT_LABEL


def generate_draft(case, ask=ask_gemini, limited=False):
    """Full draft after READY_FOR_DRAFT, or a LIMITED draft the user explicitly requests after
    STOP_UNRESOLVED. Returns 'accepted', 'discarded' or 'failed'."""
    ticket = case.start_draft(limited=limited)  # raises if the review state does not allow it
    instructions = prompts.DRAFT_INSTRUCTIONS + (prompts.LIMITED_DRAFT_RULES if limited else "")
    try:
        reply = ask(prompts.draft_input(case), instructions=instructions, json_mode=True)
    except LLMError as error:
        case.state, case.message = case_model.DRAFT_FAILED, f"Draft failed: {error}"
        return "failed"
    result = case.finish_draft(ticket, reply)  # code still rejects assertions not backed by supported findings
    if result == "accepted":
        case.draft["draft_text"] = finalize_text(case.draft["draft_text"], case.review, limited)
        case.draft["limited"] = limited
    return result


# ---- Keeping accepted reviews ----
def current_review(case):
    """The review on screen, only if it belongs to the case's current revision and snapshot."""
    r = case.review
    return r if r and (r["case_revision"], r["input_snapshot_id"]) == case.current_pair() else None


def save_review_file(case):
    """Write the just-accepted review to outputs/reviews/ right away."""
    REVIEWS_DIR.mkdir(parents=True, exist_ok=True)
    name = f"{case.case_id}-rev{case.case_revision}-{len(case.accepted_reviews)}.json"
    (REVIEWS_DIR / name).write_text(json.dumps(case.review, indent=2, ensure_ascii=False), encoding="utf-8")


# ---- Source click-through (addendum step 5) ----
def source_panel(case, finding):
    """For each cited source: the CURRENT document's title and the exact passage, or an error."""
    panel = []
    for source in finding.get("sources", []):
        doc = case.document(source.get("source_id"))
        if doc is None:
            panel.append({"source_id": source.get("source_id"), "error": "source is no longer in the case"})
        elif source.get("evidence_text") not in doc["text"]:
            panel.append({"source_id": doc["id"], "title": doc["title"], "error": "passage not found in current text"})
        else:
            panel.append({"source_id": doc["id"], "title": doc["title"], "passage": source["evidence_text"]})
    return panel
