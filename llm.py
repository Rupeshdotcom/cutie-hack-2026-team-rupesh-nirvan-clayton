"""
llm.py - one small helper to talk to Gemini.

ask_gemini(prompt) sends text to Gemini and returns its text reply.
The API key and model name come from .env, never from the code.
"""
import os
import sys

from dotenv import load_dotenv

# Load SOLARI_API_KEY, GEMINI_API_KEY and GEMINI_MODEL from the .env file.
load_dotenv()

# The Google Gen AI SDK (package "google-genai"). Friendly message if it is not installed.
try:
    from google import genai
    from google.genai import types
except ImportError:
    sys.exit("The google-genai package is missing. Run: pip install -r requirements.txt")


class LLMError(Exception):
    """Raised when a Gemini call fails, so the caller can report it in plain English."""


# ---- Setup check: are the key and model set? ----
def check_gemini_setup():
    """Exit with one friendly line if the Gemini key or model name is missing."""
    if not os.getenv("GEMINI_API_KEY"):
        sys.exit("Missing GEMINI_API_KEY in .env. Get a free key at https://aistudio.google.com/apikey")
    if not os.getenv("GEMINI_MODEL"):
        sys.exit("Missing GEMINI_MODEL in .env. Pick a free-tier model name in Google AI Studio and paste it there.")


# ---- The one function the rest of the code uses ----
def ask_gemini(prompt, instructions=None, json_mode=False):
    """Send one prompt to Gemini and return the reply text.

    instructions: the task rules, sent separately from the data (system instruction).
    json_mode: ask Gemini to reply with JSON only (code still validates it).
    """
    check_gemini_setup()
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    config = types.GenerateContentConfig(
        system_instruction=instructions,
        response_mime_type="application/json" if json_mode else None,
    )
    try:
        response = client.models.generate_content(
            model=os.getenv("GEMINI_MODEL"),
            contents=prompt,
            config=config,
        )
    except Exception as error:  # quota (429), bad key, bad model name, network...
        raise LLMError(f"Gemini call failed: {type(error).__name__}: {error}") from None
    reply = (response.text or "").strip()
    if not reply:
        raise LLMError("Gemini returned an empty reply.")
    return reply
