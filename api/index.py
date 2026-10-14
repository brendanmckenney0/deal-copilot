"""Vercel serverless entrypoint for deal-copilot.

Vercel's Python runtime serves the ASGI app named `app` from this module.
DEALCOPILOT_DATA points at /tmp (the only writable dir on serverless);
app.py cold-start bootstraps the demo index there on first invocation.
Uploads persist per warm container — fine for a demo.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("DEALCOPILOT_DATA", "/tmp/dealcopilot-data")
os.environ.setdefault("PROVIDER", "local")

from app import app  # noqa: E402,F401  (Vercel serves this ASGI app)
