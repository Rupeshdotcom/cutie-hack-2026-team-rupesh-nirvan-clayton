"""
agent.py - the adaptive research loop.

1. parse_need:  understand what must be answered
2. plan:        pick ONE next page to visit
3. browse_step: visit it (or record why it was blocked)
4. evaluate:    is the evidence enough? CONTINUE or STOP
   (steps 2-4 repeat, within MAX_ITERATIONS and MAX_PAGES)
5. summarize:   honest JSON, claims checked against the real page text
"""
import ipaddress
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

# ---- Limits: keep runs small (free plan, short demo) ----
MAX_ITERATIONS = 3   # how many plan -> browse -> evaluate rounds
MAX_PAGES = 5        # hard cap on pages visited in one run
MAX_QUOTE_CHARS = 280

# While True, browsing and Gemini are FAKED so the loop runs with no keys.
# Checkpoint C replaces the stubs with real Solari + Gemini calls.
USE_STUBS = True

PROJECT_DIR = Path(__file__).resolve().parent
SCREENSHOT_DIR = PROJECT_DIR / "outputs" / "screenshots"


# ---- Small helpers ----
def now_utc():
    """Current time as ISO 8601 UTC, e.g. 2026-11-21T21:05:00Z."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def screenshot_path_for(url):
    """Make a screenshot filename like outputs/screenshots/20261121T210500Z_example-com.png."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    host = urlparse(url).hostname or "page"
    slug = re.sub(r"[^a-z0-9]+", "-", host.lower()).strip("-")[:40]
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    return f"outputs/screenshots/{stamp}_{slug}.png"


def is_simple_public_url(url):
    """Code check on any suggested URL: plain public http(s) page, no logins, no local addresses."""
    try:
        parts = urlparse(url)
    except ValueError:
        return False
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return False
    if parts.username or parts.password:  # no user:password@ links
        return False
    host = parts.hostname.lower()
    if host == "localhost" or host.endswith((".local", ".localhost", ".internal")):
        return False
    try:
        if not ipaddress.ip_address(host).is_global:  # blocks 127.0.0.1, 192.168.x.x, ...
            return False
    except ValueError:
        pass  # a normal domain name, not a raw IP address
    path = parts.path.lower()
    if any(word in path for word in ("login", "signin", "sign-in", "signup", "account", "checkout")):
        return False
    return True


# ---- Step 1: understand the need ----
def parse_need(user_text):
    """Turn the user's text into questions to answer and what evidence would be enough."""
    # STUB: Checkpoint C asks Gemini to fill these fields.
    return {
        "text": user_text,
        "questions": [user_text],
        "enough_evidence": "A public page that directly answers the question.",
    }


# ---- Step 2: plan the next page ----
def plan(need, evidence_so_far, hint=""):
    """Pick the NEXT page only: {"url": ..., "why": ...}, or None if nothing new is worth trying."""
    tried = [e["url"] for e in evidence_so_far]
    # STUB: Checkpoint C asks Gemini, using the need, what we have, and the hint.
    url = "https://example.com"
    if url in tried:
        return None  # never visit the same page twice
    return {"url": url, "why": "stub step to prove the loop runs"}


# ---- Step 3: visit one page ----
def browse_step(step):
    """Visit ONE page. Returns an evidence record: status ok (text + screenshot) or blocked (reason)."""
    checked_at = now_utc()
    # STUB: Checkpoint C opens the page with Solari and saves a real screenshot.
    return {
        "url": step["url"],
        "status": "ok",
        "reason": "",
        "text": "Example Domain. This domain is for use in illustrative examples in documents.",
        "screenshot_path": "",
        "checked_at": checked_at,
    }


# ---- Step 4: decide CONTINUE or STOP ----
def judge_evidence(need, good_pages):
    """Is the evidence sufficient, relevant and non-contradictory? (Gemini's opinion.)"""
    # STUB: Checkpoint C asks Gemini and checks its answer is exactly CONTINUE or STOP.
    return {"decision": "STOP", "reason": "stub: one good page counts as enough", "next": ""}


def evaluate(need, evidence_so_far, iteration):
    """Return exactly one decision: CONTINUE (with reason + next idea) or STOP (with reason)."""
    good_pages = [e for e in evidence_so_far if e["status"] == "ok"]
    if good_pages:
        judgement = judge_evidence(need, good_pages)
    else:
        judgement = {"decision": "CONTINUE", "reason": "no page has loaded successfully yet",
                     "next": "try a different page"}
    # Code, not Gemini, enforces the limits.
    pages_used = len([e for e in evidence_so_far if e["status"] != "skipped"])
    if judgement["decision"] == "CONTINUE" and (iteration >= MAX_ITERATIONS or pages_used >= MAX_PAGES):
        return {"decision": "STOP", "reason": f"limits reached ({judgement['reason']})", "next": ""}
    return judgement


# ---- Step 5: honest summary ----
def draft_claims(need, evidence):
    """Propose claims with quotes and sources, plus questions we could not answer."""
    good_pages = [e for e in evidence if e["status"] == "ok"]
    # STUB: Checkpoint C asks Gemini. Here: one real quote, one fake quote to show the code check.
    claims = []
    if good_pages:
        page = good_pages[0]
        claims.append({"claim": "STUB: the page describes itself", "quote": page["text"][:80],
                       "source_url": page["url"]})
        claims.append({"claim": "STUB: fake claim (should be demoted)", "quote": "this text is not on the page",
                       "source_url": page["url"]})
    return {"claims": claims, "unverified": []}


def verify_claims(proposed, evidence):
    """Keep a claim as verified ONLY if its quote is an exact substring of that page's text."""
    pages = {e["url"]: e for e in evidence if e["status"] == "ok"}
    verified, rejected = [], []
    for item in proposed:
        claim = str(item.get("claim", "")).strip()
        quote = str(item.get("quote", ""))
        page = pages.get(str(item.get("source_url", "")))
        if not claim:
            continue
        if page is None:
            rejected.append(f"{claim} (not found: source page was not collected)")
        elif not quote or len(quote) > MAX_QUOTE_CHARS:
            rejected.append(f"{claim} (not found: quote missing or longer than {MAX_QUOTE_CHARS} characters)")
        elif quote not in page["text"]:
            rejected.append(f"{claim} (not found: quote is not on the page)")
        else:
            verified.append({
                "claim": claim,
                "status": "verified",
                "quote": quote,
                "source_url": page["url"],
                "screenshot_path": page["screenshot_path"],  # one screenshot per page, shared
                "checked_at": page["checked_at"],
            })
    return verified, rejected


def summarize(need, evidence, iterations, stop_reason):
    """Build the final JSON. Only collected evidence counts; everything else is unverified."""
    draft = draft_claims(need, evidence)
    claims, rejected = verify_claims(draft["claims"], evidence)
    unverified = list(draft["unverified"]) + rejected
    for e in evidence:  # every page we could not use, with its reason
        if e["status"] != "ok":
            unverified.append(f"{e['url']} (blocked: {e['reason']})")
    if not claims and "limits reached" in stop_reason:
        unverified.append(f"{need['text']} (limits reached)")
    return {
        "need": need["text"],
        "claims": claims,
        "unverified": unverified,
        "iterations": iterations,
        "pages_visited": [e["url"] for e in evidence if e["status"] != "skipped"],
    }


# ---- The loop ----
def run_pipeline(user_text):
    """Run parse -> (plan -> browse -> evaluate) x N -> summarize, and return the result dict."""
    need = parse_need(user_text)
    evidence = []
    iteration = 0
    hint = ""
    stop_reason = "not started"

    while iteration < MAX_ITERATIONS:
        iteration += 1
        step = plan(need, evidence, hint)
        if step is None:
            stop_reason = "no new page left to try"
            print(f"Iteration {iteration}: stopping because {stop_reason}.")
            break

        if is_simple_public_url(step["url"]):
            record = browse_step(step)
        else:  # not visited at all, just noted
            record = {"url": step["url"], "status": "skipped", "reason": "not a simple public http(s) URL",
                      "text": "", "screenshot_path": "", "checked_at": now_utc()}
        evidence.append(record)

        decision = evaluate(need, evidence, iteration)
        if decision["decision"] == "STOP":
            stop_reason = decision["reason"]
            print(f"Iteration {iteration}: checked {step['url']}; stopping because {stop_reason}.")
            break
        hint = decision["next"]
        print(f"Iteration {iteration}: checked {step['url']}; evidence insufficient because "
              f"{decision['reason']}, next I will {hint}.")

    return summarize(need, evidence, iteration, stop_reason)
