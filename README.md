# cutie-hack-2026-team-rupesh-nirvan-clayton

Cutie Hack 2026 project. **Status: scaffold in progress (Checkpoint A).** The idea is not picked yet.

Tracks: AI/ML + Data (Solari), Social Impact, Beginner

## What is here so far
- `main.py`: command-line entry point: `python main.py "describe the need here"`
- `agent.py`: the adaptive loop (understand need, pick one page, visit, decide CONTINUE/STOP, summarize). Browsing and Gemini are **stubbed** for now (`USE_STUBS = True`).
- `llm.py`: `ask_gemini(prompt)` using the `google-genai` SDK; key and model come from `.env`.
- `requirements.txt`: `solari-browser`, `google-genai`, `python-dotenv`.
- `.env.example`: copy to `.env` and fill in. `.env` is gitignored.

## Setup (Windows PowerShell)
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```
Then edit `.env` and set `GEMINI_MODEL` to a free-tier model name you verified in Google AI Studio.

_More sections (tests, limits, TODO(IDEA) points, AI tools used) are added in Checkpoint C._
