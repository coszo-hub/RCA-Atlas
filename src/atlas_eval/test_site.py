"""The HTML catalog builds from a run and embeds every case safely (run: PYTHONPATH=src python -m pytest src/atlas_eval)."""

from __future__ import annotations

import json
import re

from atlas_eval.runner import run
from atlas_eval.site import build_site
from atlas_eval.suites.base import write_jsonl


def test_catalog_embeds_every_case_and_escapes_script_text(tmp_path):
    run(["routing", "gaps", "quakes"], tmp_path, {"agent": "oracle"}, limit=3, log=lambda *_: None)
    # An answer that tries to close the data script must stay inert text.
    write_jsonl(tmp_path / "answers.jsonl", [{
        "suite": "answers", "case_id": "x-1", "case": {"id": "x-1", "question": "q", "answer_mode": "corpus"},
        "output": {"answer": "</script><script>alert(1)</script>", "answer_model": "m", "citations": [], "hits": [],
                   "latency_ms": 1.0},
        "scores": {"has_citation": False, "citations_valid": None, "empty": False, "format_ok": True,
                   "entity_recall": None, "gold_source_recall": None, "words": 3, "is_tool_task": False}}])
    page = build_site(tmp_path).read_text()
    data = re.search(r'<script type="application/json" id="data">(.*?)</script>', page, re.S)[1]
    cases = json.loads(data)["cases"]
    assert {c["suite"] for c in cases} == {"routing", "gaps", "quakes", "answers"}
    assert len(cases) == 10
    assert "<script>alert(1)" not in page
    assert "data:image/png;base64," in page and 'id="environment"' in page
