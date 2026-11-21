"""
Real-model run of every fixture case (uses Gemini and your .env; costs a few calls).

The model sees ONLY fixtures/cases.json documents. tests/answer_key.json is read
here, after the run, to check results. The scripted "user" answers every question
with "unknown", asks for a draft whenever the review is READY_FOR_DRAFT, and
deliberately requests a LIMITED draft after STOP_UNRESOLVED.
Saves everything to outputs/model_runs/ for a human to read.

Run from the project folder:  python tests/run_model_cases.py
"""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import agent  # noqa: E402
from case_model import load_fixture_case  # noqa: E402
from llm import ask_gemini  # noqa: E402

KEY = json.loads((ROOT / "tests" / "answer_key.json").read_text(encoding="utf-8"))["cases"]
OUT = ROOT / "outputs" / "model_runs"
PAUSE_SECONDS = 4  # spacing between calls to stay polite to free-tier limits (not a retry)


def paced_ask(*args, **kwargs):
    time.sleep(PAUSE_SECONDS)
    return ask_gemini(*args, **kwargs)


def run_case(case, record, max_answers=2):
    """Review -> answer 'unknown' to questions -> draft if READY. Returns the record."""
    for _ in range(max_answers + 1):
        outcome = agent.run_review(case, ask=paced_ask, log=lambda line: record["log"].append(line))
        record["outcomes"].append(outcome)
        record.setdefault("reviews", []).append(case.review)  # keep every review, even if a later call fails
        if outcome["outcome"] != agent.WAITING_FOR_ANSWER:
            break
        case.add_answer(f"q{len(case.answers) + 1}", outcome["question"], "unknown")
    record["review"] = case.review
    if case.can_generate_draft():
        record["draft_kind"] = "full"
        record["draft_result"] = agent.generate_draft(case, ask=paced_ask)
        record["draft"] = case.draft
    elif case.can_request_limited_draft():  # scripted user deliberately requests a limited draft
        record["draft_kind"] = "limited"
        record["draft_result"] = agent.generate_draft(case, ask=paced_ask, limited=True)
        record["draft"] = case.draft
    record["final_state"] = case.state
    record["final_message"] = case.message  # already a safe, fixed sentence on failures
    record["source_panels"] = {f["id"]: agent.source_panel(case, f) for f in (case.review or {}).get("findings", [])
                               if f["status"] in ("supported", "contradictory")}
    return record


def code_checks(case_id, record):
    """Mechanical checks against the answer key. Wording checks are left to a human reader."""
    expected, review, checks = KEY.get(case_id, {}), record.get("review") or {}, []
    findings = review.get("findings", [])

    def cites(status, ids):
        return any(f["status"] == status and set(ids) <= {s.get("source_id") for s in f["sources"]} for f in findings)

    for item in expected.get("supported_findings", []):
        checks.append((f"supported finding cites {item['source_id']}", cites("supported", [item["source_id"]])))
    for item in expected.get("contradictory_findings", []):
        checks.append((f"contradictory finding cites {' + '.join(item['source_ids'])}",
                       cites("contradictory", item["source_ids"])))
    if review:
        checks.append(("denial reason cites denial-fictional-1",
                       (review.get("denial_reason") or {}).get("source_id") == "denial-fictional-1"))
    bad_panels = [fid for fid, panel in record["source_panels"].items() if any("error" in p for p in panel)]
    checks.append(("every supported/contradictory source opens to its current passage", not bad_panels))
    questions = [o["question"] for o in record["outcomes"] if o.get("question")]
    checks.append(("every question asks one thing (single '?')", all(q.count("?") == 1 for q in questions)))
    draft = record.get("draft")
    if draft:
        text = draft["draft_text"]
        checks.append(("draft ends 'Draft for review. Not submitted.'", text.endswith(agent.DRAFT_LABEL)))
        sensitive = ("member id", "policy id", "policy number", "group number", "date of birth")
        checks.append(("draft has no sensitive-identifier fields", not any(s in text.lower() for s in sensitive)))
        if draft.get("limited"):
            checks.append(("limited draft starts with LIMITED label", text.startswith(agent.LIMITED_LABEL)))
            checks.append(("limited draft has visible [PLACEHOLDER: ...]", "[PLACEHOLDER:" in text))
    return [{"check": name, "pass": bool(ok)} for name, ok in checks]


def save(name, record):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{name}.json").write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n=== {name} ===")
    for line in record["log"]:
        print("  " + line)
    for o in record["outcomes"]:
        print(f"  outcome: {o['outcome']} - {o['reason']}" + (f" | Q: {o['question']}" if o.get("question") else ""))
    print(f"  draft: {record.get('draft_kind', '')} {record.get('draft_result', 'not generated')}; "
          f"final state: {record['final_state']}; message: {record['final_message']}")
    for c in record["checks"]:
        print(f"  [{'PASS' if c['pass'] else 'FAIL'}] {c['check']}")


def main():
    all_cases = ["evidence-present", "evidence-absent", "evidence-conflicting", "no-policy-excerpt",
                 "embedded-instruction"]
    for case_id in sys.argv[1:] or all_cases:  # optional: name cases to run only those
        if case_id == "step3":  # addendum step 3 alone: start from the present case minus its record
            case = load_fixture_case("evidence-present")
            case.remove_document("record-present-1")
            step3 = run_case(case, {"case_id": "evidence-present minus record-present-1", "log": [], "outcomes": []})
            step3["checks"] = code_checks("_none", step3)
            save("step3-record-removed", step3)
            continue
        case = load_fixture_case(case_id)
        record = run_case(case, {"case_id": case_id, "log": [], "outcomes": []})
        record["checks"] = code_checks(case_id, record)
        save(case_id, record)

        if case_id == "evidence-present":  # addendum step 3: remove the record after the draft
            had_draft = case.draft is not None
            case.remove_document("record-present-1")
            step3 = {"case_id": "evidence-present minus record-present-1", "log": [], "outcomes": [],
                     "cleared_immediately": had_draft and case.draft is None and case.review is None
                     and not case.can_copy_draft() and case.message == "Evidence changed. Run review again."}
            run_case(case, step3)
            step3["checks"] = [{"check": "old result cleared immediately on removal (step 2 live)",
                                "pass": step3["cleared_immediately"]}] + code_checks("_none", step3)
            save("step3-record-removed", step3)


if __name__ == "__main__":
    main()
