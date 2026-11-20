"""
ApexQuant — 5-Agent AI Football Prediction Server
==================================================

Entry point for Antideploy (and any WSGI host). Wraps server.py's Flask
app so the platform can import it directly and run it under gunicorn.

The server reads:
  - ODDS_API_KEY / FOOTBALL_API_KEY  for live match data (optional)
  - DATABASE_URL / PG*              for the prediction & learning store
  - PORT                            the port the platform listens on

Run locally:
    gunicorn -w 2 -b 0.0.0.0:${PORT:-5000} app:app
"""

import os
import sys

# Make the project directory importable when running from a tarball
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from server import app  # noqa: E402  (Flask application instance)


# ──────────────────────────────────────────────────────────
# Security headers (CSP, HSTS, X-Frame-Options, etc.)
# ──────────────────────────────────────────────────────────

@app.after_request
def _add_security_headers(resp):
    """Add the headers the platform's security scan looks for."""
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    resp.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    resp.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; script-src 'self' https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "img-src 'self' data:; font-src 'self' https://fonts.gstatic.com; "
        "connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'",
    )
    resp.headers.setdefault(
        "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
    )
    return resp


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)