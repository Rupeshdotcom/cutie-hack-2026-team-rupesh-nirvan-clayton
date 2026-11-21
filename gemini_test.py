"""
gemini_test.py - prove the Gemini connection works.

Sends one short prompt through ask_gemini() and prints the reply.
Success = a non-empty reply. The API key is never printed.
"""
import os
import sys

from llm import LLMError, ask_gemini  # llm.py loads .env and checks the key + model name


# ---- One round-trip to Gemini ----
def main():
    try:
        reply = ask_gemini("Reply with one short sentence: what is Cutie Hack?")
    except LLMError as error:
        sys.exit(f"Gemini test FAILED: {error}")
    print("Model used:", os.getenv("GEMINI_MODEL"))  # model name only, never the key
    print("Gemini replied:", reply)
    print("Gemini test PASSED.")


if __name__ == "__main__":
    main()
