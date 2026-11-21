"""
public_sources.py - read ONE allowlisted public process page with Solari.

Free plan only: launch() with no options. No logins, forms or searches.
Records the final URL actually loaded and the UTC time it was checked.
A failure returns a safe "unavailable" reason, never raw error text.
"""
import asyncio
import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from solari_browser import Solari

from safe_errors import safe_solari_error

load_dotenv()

MAX_TEXT_CHARS = 15000  # keep model input small; the stored text is what quotes are checked against


# ---- Open the page in a Solari cloud browser and read its visible text ----
async def _read_page(url):
    client = Solari(api_key=os.environ["SOLARI_API_KEY"])
    try:
        browser = await client.launch()
        page = await browser.new_page()
        await page.goto(url)
        title = await page.title()
        text = await page.inner_text("body")
        final_url = page.url
        await browser.close()
        return title, text, final_url
    finally:
        await client.close()


# ---- The one function the controller calls ----
def retrieve_public_page(url):
    """Return {"ok": True, url, title, text, checked_at} or {"ok": False, url, reason, checked_at}."""
    checked_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if not os.getenv("SOLARI_API_KEY"):
        return {"ok": False, "url": url, "reason": "SOLARI_API_KEY is missing in .env", "checked_at": checked_at}
    try:
        title, text, final_url = asyncio.run(_read_page(url))
    except Exception as error:
        return {"ok": False, "url": url, "reason": safe_solari_error(error), "checked_at": checked_at}
    text = " ".join(text.split())  # collapse whitespace so quotes can be matched exactly
    return {"ok": True, "url": final_url, "title": title, "text": text[:MAX_TEXT_CHARS], "checked_at": checked_at}
