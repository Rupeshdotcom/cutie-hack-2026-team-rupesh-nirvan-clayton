"""
main.py - command-line demo of the denial-to-draft workflow (fictional cases only).

Usage:  python main.py evidence-present
        python main.py --list
Runs the bounded review, asks you its one question if it has one, and offers a
draft only after the review says READY_FOR_DRAFT. Nothing is ever sent or filed.
The result is saved to outputs/result.json. A UI comes in a later checkpoint.
"""
import json
import sys
from pathlib import Path

import agent
from case_model import FIXTURES, load_fixture_case

OUT = Path(__file__).resolve().parent / "outputs" / "result.json"


def show_review(case):
    """Print the denial reason and each finding with its status."""
    reason = case.review.get("denial_reason") or {}
    print(f"\nDenial reason: {reason.get('summary')}")
    for f in case.review["findings"]:
        note = f" (was {f['downgraded_from']}: {'; '.join(f['source_check_problems'])})" if f.get("downgraded_from") else ""
        print(f"  [{f['status']}] {f['statement']}{note}")


def save(case, outcome):
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "case_id": case.case_id, "demo_only": True, "case_revision": case.case_revision,
        "input_snapshot_id": case.input_snapshot_id, "state": case.state, "message": case.message,
        "outcome": outcome, "answers": case.answers, "review": case.review, "draft": case.draft,
    }, indent=2, ensure_ascii=False), encoding="utf-8")


def main():
    # ---- 1. Pick a fictional case ----
    case_ids = [c["id"] for c in json.loads(FIXTURES.read_text(encoding="utf-8"))["cases"]]
    if len(sys.argv) != 2 or sys.argv[1] not in case_ids:
        print("Usage: python main.py <case-id>\nFictional cases: " + ", ".join(case_ids))
        sys.exit(0 if sys.argv[1:] == ["--list"] else 1)
    case = load_fixture_case(sys.argv[1])
    print(f"FICTIONAL DEMO CASE: {case.case_id}")

    # ---- 2. Review; answer questions until the run ends ----
    while True:
        outcome = agent.run_review(case)
        if case.review:
            show_review(case)
        print(f"\nNext action: {outcome['outcome']} - {outcome['reason']}")
        if outcome["outcome"] != agent.WAITING_FOR_ANSWER:
            break
        answer = input(f"\nQuestion: {outcome['question']}\nYour answer (blank = unknown): ").strip()
        case.add_answer(f"q{len(case.answers) + 1}", outcome["question"], answer or "unknown")
        print("Evidence changed. Running review again.")

    # ---- 3. Draft only if the review is READY_FOR_DRAFT and you ask for it ----
    if case.can_generate_draft() and input("\nGenerate a draft? (y/n): ").strip().lower() == "y":
        result = agent.generate_draft(case)
        print("\n" + (case.draft["draft_text"] if result == "accepted" else case.message))

    save(case, outcome)
    print(f"\nSaved to outputs/result.json (state: {case.state})")


if __name__ == "__main__":
    main()
