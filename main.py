"""
main.py - command-line entry point.

Usage:  python main.py "describe the need here"
Runs the agent loop, prints the result, and saves it to outputs/result.json.
"""
import json
import sys

import agent
from llm import LLMError


def main():
    # ---- 1. Read the need from the command line ----
    user_text = " ".join(sys.argv[1:]).strip()
    if not user_text:
        print('Please describe the need, e.g.: python main.py "describe the need here"')
        sys.exit(1)

    if agent.USE_STUBS:
        print("Note: running with STUBS (fake browsing and fake Gemini). No API calls are made.")

    # ---- 2. Run the agent loop ----
    try:
        result = agent.run_pipeline(user_text)
    except LLMError as error:
        print(f"Stopped: {error}")
        sys.exit(1)

    # ---- 3. Save and show the result ----
    out_path = agent.PROJECT_DIR / "outputs" / "result.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    print("Saved result to outputs/result.json")


if __name__ == "__main__":
    main()
