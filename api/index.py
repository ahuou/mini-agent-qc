"""Vercel serverless entrypoint.

On Vercel a FastAPI app is served as a single Function: the platform looks for an
ASGI instance named ``app`` here and ``vercel.json`` rewrites every route to it.
We just (a) make the repo packages importable and (b) keep the only writable
paths under ``/tmp`` (the sole writable dir on serverless).
"""

import os
import sys
from pathlib import Path

# Repo root on the path so `webapp` / `qc_pipeline` import inside the function.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Writable, ephemeral cache location on serverless (results.json already uses a
# tempfile dir, which resolves to /tmp here).
os.environ.setdefault("QC_CACHE_DIR", "/tmp/qc_pipeline_cache")

from webapp.server import app  # noqa: E402  -- the ASGI instance Vercel serves

__all__ = ["app"]
