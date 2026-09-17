"""Vercel serverless entry point.

Vercel does not run `python app.py`; it imports a WSGI callable named `app`
from a file under api/. The repository root goes on the path first so the
Flask app and its templates/ folder resolve exactly as they do locally.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app  # noqa: E402  (must follow the sys.path change)

__all__ = ['app']
