"""
safe_errors.py - turn a Solari/browser failure into a short, safe sentence.

Raw error text can contain session IDs or URLs with tokens, so it is NEVER shown
or logged. We only use the HTTP status, a known Solari error code, or the error's
type name, and map them to fixed plain-English messages.
"""
from solari_browser import SolariError

# Fixed messages for known Solari error codes (from solari_browser/errors.py).
CODE_MESSAGES = {
    "FeatureRequiresPlan": "this feature needs a paid Solari plan (not used here)",
    "ConcurrencyLimitExceeded": "too many Solari browsers are open at once",
    "PlanLimitExceeded": "the Solari plan limit has been reached",
    "BrowserUnhealthy": "the Solari browser was not healthy",
}

# Fixed messages for HTTP statuses.
STATUS_MESSAGES = {
    401: "the Solari API key was rejected (check SOLARI_API_KEY in .env)",
    403: "Solari refused access for this API key",
    402: "Solari says this needs a paid plan (HTTP 402)",
    404: "Solari could not find that session",
    429: "Solari rate limit or quota reached (HTTP 429)",
}


def safe_solari_error(error):
    """Return a safe one-line description. Never includes the raw error message."""
    if isinstance(error, SolariError):
        if error.code in CODE_MESSAGES:
            return f"Solari error: {CODE_MESSAGES[error.code]}"
        if error.status in STATUS_MESSAGES:
            return f"Solari error: {STATUS_MESSAGES[error.status]}"
        if isinstance(error.status, int) and error.status >= 500:
            return f"Solari error: the service had a temporary problem (HTTP {error.status})"
        if isinstance(error.status, int):
            return f"Solari error: request failed (HTTP {error.status})"
        return "Solari error: could not reach the Solari service"
    name = type(error).__name__
    if "Timeout" in name:
        return "Browser error: the page took too long to load"
    return f"Browser error: unexpected {name} (details hidden for safety)"
