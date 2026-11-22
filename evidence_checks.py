"""
evidence_checks.py - code checks on what the model returns.

The model proposes; this file decides what is allowed to count.
A source check proves a quote really is in that document (provenance).
It does NOT prove the model's interpretation is right or that coverage is owed.
"""
import json

STATUSES = ("supported", "missing", "contradictory", "not_established")
ACTIONS = ("ASK_USER", "RETRIEVE_PUBLIC_GUIDANCE", "READY_FOR_DRAFT", "STOP_UNRESOLVED")


class ModelOutputError(Exception):
    """The model's reply was not usable. Shown as a failed state, never as an empty success."""


# ---- Step 1: is it JSON at all? ----
def parse_model_json(text):
    """Parse the model's reply as a JSON object, allowing an optional ```json fence."""
    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned[4:] if cleaned.lower().startswith("json") else cleaned
    try:
        data = json.loads(cleaned)
    except ValueError:
        raise ModelOutputError("the model did not return valid JSON") from None
    if not isinstance(data, dict):
        raise ModelOutputError("the model returned JSON, but not an object")
    return data


# ---- Step 2: does each quoted passage really appear in that document? ----
def source_problem(source, documents):
    """Return None if the source is fine, else a short plain-English problem."""
    if not isinstance(source, dict):
        return "source is not an object"
    doc = next((d for d in documents if d["id"] == source.get("source_id")), None)
    if doc is None:
        return f"source {source.get('source_id')!r} is not in the current case"
    passage = source.get("evidence_text")
    if not isinstance(passage, str) or not passage:
        return f"no passage given for {doc['id']}"
    if passage not in doc["text"]:
        return f"passage not found in {doc['id']}"
    return None


def check_finding(finding, documents):
    """Validate one finding. A supported/contradictory claim with bad sources is downgraded, not dropped."""
    if not isinstance(finding, dict) or not finding.get("id") or not finding.get("statement"):
        raise ModelOutputError("a finding is missing its id or statement")
    if finding.get("status") not in STATUSES:
        raise ModelOutputError(f"finding {finding['id']} has unknown status {finding.get('status')!r}")
    sources = finding.get("sources") or []
    if not isinstance(sources, list):
        raise ModelOutputError(f"finding {finding['id']} sources is not a list")
    problems = [p for p in (source_problem(s, documents) for s in sources) if p]
    valid = [s for s in sources if isinstance(s, dict) and source_problem(s, documents) is None]
    good = len({s.get("source_id") for s in valid})

    checked = dict(finding, sources=sources, source_check_problems=problems)
    needed = {"supported": 1, "contradictory": 2}.get(finding["status"], 0)
    if needed and (problems or good < needed):
        checked["status"] = "not_established"
        checked["downgraded_from"] = finding["status"]
        if good < needed:
            problems.append(f"{finding['status']} needs at least {needed} valid source(s)")
    # Keep user-reported support labelled as user-reported.
    checked["user_reported"] = any(
        next((d["kind"] for d in documents if d["id"] == s.get("source_id")), "") == "user_report"
        for s in sources if isinstance(s, dict))
    return checked


def check_review(data, documents):
    """Validate a whole review reply against the current documents."""
    findings = data.get("findings")
    if not isinstance(findings, list):
        raise ModelOutputError("the review has no findings list")
    checked = [check_finding(f, documents) for f in findings]
    ids = [f["id"] for f in checked]
    if len(ids) != len(set(ids)):
        raise ModelOutputError("two findings share the same id")

    reason = data.get("denial_reason") or {}
    if reason.get("source_id"):
        reason = dict(reason, source_check_problem=source_problem(reason, documents))

    action = data.get("next_action") or {}
    if action.get("action") not in ACTIONS:
        raise ModelOutputError(f"next action {action.get('action')!r} is not one of {', '.join(ACTIONS)}")
    unknown = [i for i in action.get("related_finding_ids") or [] if i not in ids]
    if unknown:
        raise ModelOutputError(f"next action refers to unknown findings {unknown}")

    return {
        "denial_reason": reason,
        "findings": checked,
        "next_action": action,
        "limitations": list(data.get("limitations") or []),
    }


# ---- Step 3: the draft may only lean on supported findings from the current review ----
def check_draft(data, review):
    """Reject a draft whose assertions cite anything but supported findings of this review."""
    if not isinstance(data.get("draft_text"), str) or not data["draft_text"].strip():
        raise ModelOutputError("the draft has no text")
    if not data.get("assertions"):
        raise ModelOutputError("the draft lists no assertions, so its claims cannot be checked")

    supported = {f["id"] for f in review["findings"] if f["status"] == "supported"}
    for assertion in data.get("assertions") or []:
        cited = assertion.get("finding_ids") or []
        bad = [i for i in cited if i not in supported]
        if not cited or bad:
            raise ModelOutputError(f"a draft assertion is not backed by a supported finding ({bad or 'none cited'})")
    return {
        "status": "needs_review",
        "draft_text": data["draft_text"],
        "assertions": list(data.get("assertions") or []),
        "missing_before_send": list(data.get("missing_before_send") or []),
        "review_notes": list(data.get("review_notes") or []),
    }
