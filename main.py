"""Vercel entrypoint — `@vercel/python` (see vercel.json) serves the `app` here.

`builds` in vercel.json invokes the Python builder, which installs
requirements.txt and bundles the project (via includeFiles). Repo root is added
to sys.path so `webapp` / `qc_pipeline` import cleanly; ANTHROPIC_API_KEY and
QC_CACHE_DIR come from Vercel env vars (we default the cache to /tmp here too).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("QC_CACHE_DIR", "/tmp/qc_pipeline_cache")

from webapp.server import app  # noqa: E402  -- ASGI instance Vercel serves

__all__ = ["app"]
