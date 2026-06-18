"""Extraction cache: identical (model, notes) is served from disk, never re-called."""

from qc_pipeline.cache import CachingExtractor, ExtractionCache
from qc_pipeline.config import Config
from qc_pipeline.extraction.base import CallMeta, Extractor
from qc_pipeline.extraction.schema import DefectExtraction
from qc_pipeline.pipeline import run_pipeline


class CountingExtractor(Extractor):
    """Records how many times the (expensive) extract was actually invoked."""
    name = "counting"

    def __init__(self):
        self.calls = 0

    def extract(self, major_note, minor_note, *, context=None):
        self.calls += 1
        return (
            DefectExtraction(
                major_defects=len(major_note.split()), minor_defects=len(minor_note.split()),
                major_confidence=0.9, minor_confidence=0.9,
                major_evidence=major_note[:12], minor_evidence=minor_note[:12]),
            CallMeta(model="claude-test", input_tokens=100, output_tokens=20),
        )


def test_cache_hit_skips_the_inner_call(tmp_path):
    inner = CountingExtractor()
    cx = CachingExtractor(inner, ExtractionCache(tmp_path), namespace="claude-test")
    e1, m1 = cx.extract("No critical failures.", "13 hundred units")
    assert inner.calls == 1 and m1.cached is False
    e2, m2 = cx.extract("No critical failures.", "13 hundred units")
    assert inner.calls == 1                      # not called again
    assert m2.cached is True
    assert m2.input_tokens == 0 and m2.output_tokens == 0   # no new spend
    assert (e2.major_defects, e2.minor_defects) == (e1.major_defects, e1.minor_defects)


def test_cache_miss_on_changed_notes(tmp_path):
    inner = CountingExtractor()
    cx = CachingExtractor(inner, ExtractionCache(tmp_path), namespace="claude-test")
    cx.extract("a", "b")
    cx.extract("a", "c")            # different minor note -> miss
    assert inner.calls == 2


def test_cache_separated_by_model_namespace(tmp_path):
    inner = CountingExtractor()
    cache = ExtractionCache(tmp_path)
    CachingExtractor(inner, cache, namespace="claude-haiku-4-5").extract("a", "b")
    CachingExtractor(inner, cache, namespace="claude-opus-4-8").extract("a", "b")
    assert inner.calls == 2         # same notes, different model -> separate entries


def test_cache_persists_across_instances(tmp_path):
    inner = CountingExtractor()
    CachingExtractor(inner, ExtractionCache(tmp_path), namespace="m").extract("x", "y")
    assert inner.calls == 1
    inner2 = CountingExtractor()    # fresh wrapper + fresh cache object, same dir
    _, m = CachingExtractor(inner2, ExtractionCache(tmp_path), namespace="m").extract("x", "y")
    assert inner2.calls == 0 and m.cached is True


def test_pipeline_second_run_is_fully_cached(tmp_path):
    cache = ExtractionCache(tmp_path / "c")
    inner = CountingExtractor()
    cfg = Config(mode="mock", results_dir=tmp_path / "r")
    cx = CachingExtractor(inner, cache, namespace="test")

    m1 = run_pipeline(cfg, extractor=cx)
    n = m1["run"]["n_reports"]
    assert inner.calls == n                      # first run: one call per report

    inner.calls = 0
    m2 = run_pipeline(cfg, extractor=cx)
    assert inner.calls == 0                      # second run: everything from cache
    assert m2["cost"]["cache_hits"] == n
