"""Content-addressed extraction cache.

The only expensive, token-burning step is the LLM extraction of one report's
audit notes. Re-reading the *same notes with the same model* is wasted spend, so
``CachingExtractor`` keys each extraction by a hash of (cache version, model
namespace, major note, minor note) and persists the structured result to disk.
A re-run on identical content is served from disk — no API call, no tokens.

Editing a note changes its hash → cache miss → it re-extracts (correct). The hash
covers only the notes (what the model reads), not the whole file, so changing an
unrelated field like ``total_products`` does not force a re-read (the threshold
rules recompute cheaply anyway). Bump ``CACHE_VERSION`` if the extraction prompt
changes in a way that should invalidate stored results.

Entries are one JSON file per key, which keeps concurrent writes (the parallel
live path) race-free. Failures are non-fatal — a cache problem degrades to a
normal extraction, never an error.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Optional

from .extraction.base import CallMeta, Extractor
from .extraction.schema import DefectExtraction

CACHE_VERSION = "v1"


class ExtractionCache:
    """A tiny on-disk key→entry store (one JSON file per key)."""

    def __init__(self, cache_dir: Path | str):
        self.dir = Path(cache_dir)
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

    def _path(self, key: str) -> Path:
        return self.dir / f"{key}.json"

    def get(self, key: str) -> Optional[dict]:
        p = self._path(key)
        if p.is_file():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                return None
        return None

    def put(self, key: str, entry: dict) -> None:
        try:
            self._path(key).write_text(json.dumps(entry), encoding="utf-8")
        except Exception:
            pass

    def stats(self) -> dict:
        try:
            n = sum(1 for _ in self.dir.glob("*.json"))
        except Exception:
            n = 0
        return {"entries": n, "dir": str(self.dir)}

    def clear(self) -> int:
        cleared = 0
        try:
            for p in self.dir.glob("*.json"):
                try:
                    p.unlink()
                    cleared += 1
                except Exception:
                    pass
        except Exception:
            pass
        return cleared


class CachingExtractor(Extractor):
    """Wraps any extractor, serving repeat (model, notes) reads from disk."""

    def __init__(self, inner: Extractor, cache: ExtractionCache, namespace: str):
        self.inner = inner
        self.cache = cache
        self.namespace = namespace
        self.name = inner.name

    def _key(self, major_note: str, minor_note: str) -> str:
        h = hashlib.sha256()
        for part in (CACHE_VERSION, self.namespace, major_note, minor_note):
            h.update(part.encode("utf-8"))
            h.update(b"\x1f")
        return h.hexdigest()[:40]

    def extract(self, major_note, minor_note, *, context=None):
        key = self._key(major_note, minor_note)
        hit = self.cache.get(key)
        if hit is not None:
            try:
                extraction = DefectExtraction(**hit["extraction"])
                return extraction, CallMeta(model=hit.get("model"), cached=True)
            except Exception:
                pass  # corrupt/old entry — fall through and recompute

        extraction, meta = self.inner.extract(major_note, minor_note, context=context)
        self.cache.put(key, {"extraction": extraction.model_dump(), "model": meta.model})
        return extraction, meta
