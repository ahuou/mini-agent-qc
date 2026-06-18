"""Quality-Control Pipeline: read inspection reports, extract defect counts from
free-text audit notes with an LLM, apply threshold rules, alert stakeholders,
and measure the tool's own extraction quality.

Public entry point: ``qc_pipeline.pipeline.run_pipeline``.
"""

__version__ = "1.0.0"
