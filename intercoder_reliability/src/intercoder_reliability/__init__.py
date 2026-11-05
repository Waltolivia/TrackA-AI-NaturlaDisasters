"""Intercoder reliability coding and agreement for Track A AI responses.

This module is deliberately separate from collection. It reads the archived
``responses.json`` files produced by ``ai_probe_runner``/``pipeline_worker``,
exports provider-blind coding worksheets, and computes agreement statistics for
the study rubric.
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "0.1.0"
