"""
quote_compare.py - compare two supplied estimates for the SAME service, in whole cents.

Code does the arithmetic, never the model. Zero is a real amount; missing is not zero.
If anything makes the totals not comparable, no "winner" is named.
"""


def is_amount(value):
    """A real amount is a whole number of cents, 0 or more (True/False do not count)."""
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def compare_quotes(q):
    """Return status, which immediate estimate is lower, and by how many cents."""
    not_comparable = {"status": "not_comparable", "lower_immediate_estimate": None, "difference_cents": None}

    # ---- Same service, same setting, same scope? ----
    if not (q.get("same_service_confirmed") and q.get("same_setting_confirmed")):
        return dict(not_comparable, next_question="Do both estimates cover the same service in the same setting?")
    if not q.get("insurance_estimate_comparable_scope"):
        return dict(not_comparable, next_question="Does the insurance estimate cover the same parts of the service?")

    # ---- Is the cash total complete? ----
    if not q.get("cash_includes_professional_fees"):
        return dict(not_comparable, next_question="What is the separately billed professional fee?")
    if not q.get("cash_includes_facility_fees"):
        return dict(not_comparable, next_question="What is the separately billed facility fee?")

    # ---- Are both amounts known? (0 is known) ----
    cash, insurance = q.get("cash_total_cents"), q.get("insurance_patient_estimate_cents")
    if not (is_amount(cash) and is_amount(insurance)):
        return dict(not_comparable, next_question="What are both complete estimated amounts?")

    # ---- Arithmetic in integer cents ----
    if cash == insurance:
        lower = "equal"
    else:
        lower = "cash" if cash < insurance else "insurance"
    return {
        "status": "comparable_estimates",
        "lower_immediate_estimate": lower,
        "difference_cents": abs(cash - insurance),
        "annual_best_known": False,  # immediate estimates only; not a final bill or annual choice
        "deductible_credit": q.get("deductible_credit", "unknown"),
    }
