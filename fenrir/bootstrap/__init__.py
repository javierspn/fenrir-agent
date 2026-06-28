"""Idempotent bootstrap: models -> anchors -> relations -> benchmarks -> marker.

Entry point: ``python -m fenrir.bootstrap`` (see __main__.py). Each sub-step is
independently idempotent so an interrupted run resumes without duplication
(FR-012/017/018; contracts/bootstrap.contract.md).
"""
