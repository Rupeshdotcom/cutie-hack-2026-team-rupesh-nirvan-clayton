"""
solari_test.py - prove the Solari browser works.

Opens https://example.com in a Solari cloud browser (free plan: launch() with no options),
prints the page title, and saves outputs/screenshots/solari_test.png.
Success = it prints "Example Domain" and the screenshot file exists.
"""
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# ---- Setup: load the key from .env and fail kindly if it is missing ----
load_dotenv()
if not os.getenv("SOLARI_API_KEY"):
    sys.exit("Missing SOLARI_API_KEY in .env. Create a key at https://console.getsolari.com (API Keys tab).")

from solari_browser import Solari  # imported after the key check so the error above stays simple

from safe_errors import safe_solari_error  # never print raw error text (may hold session IDs)

SCREENSHOT = Path(__file__).resolve().parent / "outputs" / "screenshots" / "solari_test.png"


# ---- The test: launch, open, read title, screenshot, close ----
async def main():
    client = Solari(api_key=os.environ["SOLARI_API_KEY"])
    try:
        browser = await client.launch()  # no options: free plan only
        page = await browser.new_page()
        await page.goto("https://example.com")
        print("Page title:", await page.title())
        SCREENSHOT.parent.mkdir(parents=True, exist_ok=True)
        await page.screenshot(path=str(SCREENSHOT))
        await browser.close()  # ends the cloud browser session
    finally:
        await client.close()  # releases the connection


# ---- Run it and report in plain English ----
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as error:  # 402 (paid feature), auth, timeout, network...
        sys.exit(f"Solari test FAILED: {safe_solari_error(error)}")
    if SCREENSHOT.exists():
        print("Solari test PASSED. Screenshot saved to outputs/screenshots/solari_test.png")
    else:
        sys.exit("Solari test FAILED: the screenshot file was not created.")
