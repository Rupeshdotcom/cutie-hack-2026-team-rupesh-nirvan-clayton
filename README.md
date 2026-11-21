# Denial Evidence Review (Cutie Hack 2026)

A same-day hackathon prototype that helps a person prepare a response to a medical-insurance denial. You load a **fictional** case (a denial, a policy excerpt and some facts). Gemini reviews the evidence: which statements are supported, missing, contradictory or not established, each with the exact source passage. A bounded agent then picks **one** next step: ask you one question, read one public guidance page through Solari, say the case is ready for a draft, or stop because something can't be resolved. Drafts are for human review only. Nothing is ever sent, filed or submitted.

This is not medical, legal or coverage advice, and it does not decide whether an appeal will succeed. Similar tools already exist; this project is about a careful, traceable workflow, not a new invention.

Tracks: AI/ML + Data (Solari), Social Impact, Beginner

## How to run it

**Setup (Windows PowerShell, Python 3.9+):**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install --only-binary cryptography -r requirements.txt
copy .env.example .env
```
(`--only-binary cryptography` avoids a failed source build on Windows ARM laptops; elsewhere plain `pip install -r requirements.txt` works.)

Then open `.env` in an editor and fill in your own values: `SOLARI_API_KEY`, `GEMINI_API_KEY`, and `GEMINI_MODEL` (a free-tier model name you checked in Google AI Studio). `.env` is gitignored. Never paste keys anywhere else.

**Start the website:**
```powershell
.\.venv\Scripts\python.exe server.py
```
Then open **http://127.0.0.1:8000** in your browser, and press Ctrl+C in the terminal to stop. The server only listens on your own computer. All Gemini and Solari calls happen in Python on the server, and API keys never reach the page.

**On the page:** pick a fictional case → Run review → answer the one question (or "I don't know") → Run review again → Generate draft (after READY_FOR_DRAFT) or Request limited draft (after STOP_UNRESOLVED) → Copy.

**Other ways to run:**
- Command line: `python main.py evidence-present` (or `python main.py --list`)
- Connection checks: `python solari_test.py` and `python gemini_test.py`
- Offline tests, with no network and no API calls: `python -m unittest discover -s tests -v`
- Real-model runs of the fixture cases, which use Gemini calls: `python tests/run_model_cases.py evidence-absent embedded-instruction step3`

## What is fictional
- **Every case and document** (denial, policy excerpt, referral, treatment records, user reports) is made up and labelled fictional, in `fixtures/cases.json`. There is no real patient, clinician, insurer or policy.
- **The expected answers** used to check results live separately in `tests/answer_key.json`. They are **never** sent to the model, and the loader refuses any input file that contains them.
- **The fictional cases are:**
  - `evidence-present`: the required record is supplied;
  - `evidence-absent`: only the user's recollection;
  - `evidence-conflicting`: the user report and the signed record disagree;
  - `no-policy-excerpt`: the policy text is missing;
  - `embedded-instruction`: a document tries to give the AI instructions.

## What is live
- **Solari:** one real retrieval of a public process page, `https://www.healthcare.gov/appeal-insurance-company-decision/internal-appeals/`. It is the only allowed URL, and code enforces that.
  - **How it runs:** the page is read on Solari's free plan (`launch()` with no options, no logins or forms). The app records the actual final URL and the UTC time it was checked, and shows both in the Public guidance panel.
  - **What happens next:** the page is added as evidence and the case is reviewed again in the same run, without new budget.
  - **Its limits:** the page describes a general appeal process. It does not establish this case's coverage, plan type or deadlines.
- **Gemini** (`google-genai`, model set by `GEMINI_MODEL`) writes the evidence review and the drafts.
- **Code, not the model, enforces the rules:**
  - every quoted passage must appear exactly in its source, or the finding is downgraded;
  - one action per review, at most 3 review cycles and 2 retrievals per case revision, and no repeated questions or URLs;
  - drafts may only assert supported findings;
  - any edit or answer clears old results ("Evidence changed. Run review again."), and late replies from before an edit are discarded.

  A quote check proves the passage is real; it does not prove the interpretation is right.

## What is saved and what is fallback
- **There is no saved or cached copy of the guidance page.** If Solari can't read it (timeout, block, error), the panel says **Unavailable** with a plain reason, the URL tried and the time. The app never shows an old copy as if it were live.
- **Error messages:** Gemini and Solari errors are shown only as fixed plain sentences, such as "Gemini rate limit or free-tier quota reached (HTTP 429)". Raw error text is never shown or saved.
- **Local files** go to `outputs/`, which is gitignored:
  - each accepted review is saved immediately in `outputs/reviews/`;
  - CLI results go to `outputs/result.json`;
  - real-model test runs go to `outputs/model_runs/`.
- **Case state:** the website keeps one case in memory for one person. Nothing is stored permanently, and there are no accounts or database.

## What has been verified (observed on November 21, 2026)
- **Offline tests (38):** all pass. They cover source checks, discarding stale results, the controller's limits, the limited draft, safe error messages, the retrieval path and the website API.
- **Live Solari:** retrieving the healthcare.gov page worked. The title was "Internal appeals | HealthCare.gov", the final URL was unchanged, and the time was recorded.
- **Real Gemini reviews:**
  - **evidence-present:** the review and a full draft passed every check. The draft doesn't claim the record was already submitted, and has no invented deadline or guarantee.
  - **conflicting:** the review cites both conflicting sources.
  - **no-policy:** the review marks the policy as missing.
  - **record-removed:** the review marks completion as missing and asks for the record.
  - **evidence-absent:** the review asked one single question, and completion was never asserted.
  - **embedded-instruction:** the review treated the injected instruction as text, not evidence.
- **The website:** the full flow worked in a browser at phone and laptop widths using fake model replies. In a live run it correctly showed the 429 quota error as "Review failed".

## Not yet verified — Gemini free-tier quota reached during the event
- A real review and draft through the website
- The evidence-absent draft
- The embedded-instruction draft
- The limited draft after the record is removed (addendum step 3)
- Drafts for the conflicting and no-policy cases (those reviews stopped unresolved before the limited-draft option existed)
- Gemini itself choosing to retrieve the guidance page inside a full live run. The retrieval was tested live on its own, and inside the controller with fake replies.

## Limits
- Fictional cases only, one denial type, and a policy excerpt rather than a full contract.
- No accounts, uploads, OCR, submissions, insurer connections, or medical or legal judgments.
- Drafts contain visible `[PLACEHOLDER: ...]` text for anything unresolved. The draft prompt forbids fields for sensitive identifiers such as member ID or date of birth. That rule lives in the prompt, not in code. With a live draft: not yet verified — Gemini free-tier quota reached during the event.

## Files
- `server.py` + `static/index.html`: the local website
- `agent.py`: the bounded controller (one action per review, limits, limited draft, source panel)
- `prompts.py`: the review and draft instructions sent to Gemini
- `case_model.py`: case revision, snapshot ID, stale-result rules
- `evidence_checks.py`: code checks on model output
- `public_sources.py`: the Solari retrieval
- `llm.py`: the Gemini call
- `safe_errors.py`: safe error sentences
- `main.py`: command-line version
- `solari_test.py`, `gemini_test.py`: connection checks
- `fixtures/cases.json`: fictional inputs
- `tests/`: answer key, offline tests and real-model runner

## AI tools used
- **Claude Code** (Anthropic, Claude Opus 5.5) was the coding assistant. It wrote most of the code, tests and this README under the team's direction. The team set the requirements and reviewed each checkpoint. Inside Claude Code we also used two community skills: `find-skills` (vercel-labs) and `deslop` (cursor/plugins, a checklist for removing unnecessary AI-style code clutter).
- **Google Gemini** (via `google-genai`) is used **at runtime** inside the app for the evidence review and the drafts.
- **Solari** is the cloud browser the app uses for the live public-page retrieval. It is not an AI model.
