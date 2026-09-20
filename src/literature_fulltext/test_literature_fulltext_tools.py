import hashlib
import json
import os
import socket
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from literature_fulltext_tools import (
    REQUIRED_REASON,
    LiteratureFullTextToolkit,
    TOOL_SCHEMAS,
    dispatch,
    normalize_doi,
)


class RecordingToolkit(LiteratureFullTextToolkit):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.acquire_calls = 0

    def _acquire(self, row, *, max_pages, max_ocr_pages):
        self.acquire_calls += 1
        chunks = [{
            "chunk_id": "FULLTEXT-test",
            "work_id": row["id"],
            "page": 3,
            "section": "Results",
            "position": 0,
            "text": "The cabled sensor measured hydrothermal temperature continuously and detected a strong anomaly after the event.",
            "word_count": 15,
            "source_is_untrusted_data": True,
        }]
        metadata = {
            "work_id": row["id"], "source_url": "https://example.org/paper.pdf",
            "retrieved_at": "2026-01-01T00:00:00Z", "sha256": "a" * 64,
            "content_type": "application/pdf", "page_count": 7,
        }
        return {"ok": True, "cache": {"metadata": metadata, "chunks": chunks, "root": self.cache_dir / row["id"]}, "attempts": [{"result": "fixture"}]}


class FullTextTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.corpus = self.root / "literature.jsonl"
        rows = [
            {
                "id": "COSZO-REF-064", "canonical_id": "COSZO-REF-064",
                "resolved_title": "Estuarine Circulation", "resolved_doi": "10.1029/2020JC016738",
                "citation": "Example citation", "abstract": "Relevant abstract.", "abstract_status": "retrieved",
                "full_text_url": "https://example.org/paper.pdf", "full_text_status": "verified_reachable_during_collection",
                "paper_url": "https://doi.org/10.1029/2020JC016738", "source_links": [],
                "source_occurrence_ids": ["COSZO-REF-064", "COSZO-REF-066"],
                "source_occurrences": [{"occurrence_id": "ZOTERO-ALIAS"}], "license": "CC-BY",
            },
            {
                "id": "COSZO-REF-047", "canonical_id": "COSZO-REF-047",
                "resolved_title": "Proposal", "resolved_doi": None, "citation": "Proposal",
                "abstract": "Cover sheet", "abstract_status": "retrieved",
                "full_text_url": "https://example.org/cover.pdf", "full_text_status": "retrieved_proposal_cover_sheet_only",
                "paper_url": "https://example.org/cover.pdf", "source_links": [],
                "source_occurrence_ids": ["COSZO-REF-047"], "source_occurrences": [], "license": None,
            },
        ]
        self.corpus.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
        self.cache = self.root / "runtime"
        self.toolkit = RecordingToolkit(self.corpus, self.cache)

    def tearDown(self):
        self.temp.cleanup()

    def test_selector_resolution_and_doi_normalization(self):
        by_alias = self.toolkit.status(occurrence_id="COSZO-REF-066")
        self.assertTrue(by_alias["ok"])
        self.assertEqual(by_alias["work"]["work_id"], "COSZO-REF-064")
        by_zotero = self.toolkit.status(occurrence_id="zotero-alias")
        self.assertEqual(by_zotero["work"]["work_id"], "COSZO-REF-064")
        by_doi = self.toolkit.status(doi="HTTPS://DOI.ORG/10.1029/2020jc016738")
        self.assertEqual(by_doi["work"]["work_id"], "COSZO-REF-064")
        self.assertEqual(normalize_doi("doi:10.1029/2020JC016738"), "10.1029/2020jc016738")

    def test_exactly_one_selector_is_required(self):
        self.assertEqual(self.toolkit.status()["error"]["type"], "invalid_selector")
        result = self.toolkit.status(work_id="COSZO-REF-064", doi="10.1029/2020JC016738")
        self.assertEqual(result["error"]["type"], "invalid_selector")

    def test_status_and_cache_only_mode_never_fetch(self):
        self.assertTrue(self.toolkit.status(work_id="COSZO-REF-064")["ok"])
        result = self.toolkit.evidence(
            work_id="COSZO-REF-064", question="temperature anomaly",
            retrieval_reason=REQUIRED_REASON, fetch_if_missing=False,
        )
        self.assertEqual(result["access_status"], "not_cached")
        self.assertEqual(self.toolkit.acquire_calls, 0)

    def test_fetch_requires_abstract_insufficiency_reason(self):
        result = self.toolkit.evidence(
            work_id="COSZO-REF-064", question="temperature anomaly", retrieval_reason="interesting_paper"
        )
        self.assertEqual(result["error"]["type"], "retrieval_not_justified")
        self.assertEqual(self.toolkit.acquire_calls, 0)

    def test_explicit_evidence_call_fetches_once_and_returns_bounded_locator(self):
        result = self.toolkit.evidence(
            occurrence_id="COSZO-REF-066", question="What temperature anomaly was detected?",
            retrieval_reason=REQUIRED_REASON,
        )
        self.assertTrue(result["ok"])
        self.assertTrue(result["network_used"])
        self.assertEqual(self.toolkit.acquire_calls, 1)
        self.assertEqual(result["passages"][0]["page"], 3)
        self.assertLessEqual(sum(len(item["text"]) for item in result["passages"]), 8000)

    def test_cover_sheet_is_not_an_eligible_full_text_candidate(self):
        result = self.toolkit.status(work_id="COSZO-REF-047")
        candidate = next(item for item in result["candidate_hints"] if item["source_field"] == "full_text_url")
        self.assertFalse(candidate["eligible_for_fetch"])

    def test_cache_integrity_and_zero_network_reuse(self):
        row = self.toolkit.by_id["coszo-ref-064"]
        body = ("<html><body><h1>Results</h1><p>" + "hydrothermal temperature anomaly " * 350 + "</p></body></html>").encode()
        parsed = self.toolkit._parse_html(body, "https://example.org/article")
        self.assertTrue(parsed["is_full_text"])
        response = {"final_url": "https://example.org/article", "content_type": "text/html", "etag": None, "last_modified": None}
        self.toolkit._cache_html(row, body, response, parsed)
        canonical_before = hashlib.sha256(self.corpus.read_bytes()).hexdigest()
        fresh = RecordingToolkit(self.corpus, self.cache)
        result = fresh.evidence(
            work_id="COSZO-REF-064", question="hydrothermal temperature anomaly",
            retrieval_reason=REQUIRED_REASON,
        )
        self.assertEqual(result["evidence_mode"], "validated_cache")
        self.assertEqual(fresh.acquire_calls, 0)
        self.assertEqual(hashlib.sha256(self.corpus.read_bytes()).hexdigest(), canonical_before)
        self.assertTrue(str(self.cache).startswith(str(self.root)))

    def test_ssrf_guards_block_private_dns_and_credentials(self):
        with patch("literature_fulltext_tools.socket.getaddrinfo", return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.8", 443))]):
            with self.assertRaisesRegex(ValueError, "non-public"):
                self.toolkit._validate_url("https://example.org/paper.pdf")
        with self.assertRaisesRegex(ValueError, "credential-bearing"):
            self.toolkit._validate_url("https://user:pass@example.org/paper.pdf")
        with self.assertRaisesRegex(ValueError, "internal hostnames"):
            self.toolkit._validate_url("http://localhost/paper.pdf")

    def test_pdf_extraction_retains_page_provenance(self):
        try:
            from reportlab.pdfgen import canvas
        except ImportError:
            self.skipTest("reportlab unavailable")
        pdf = self.root / "fixture.pdf"
        c = canvas.Canvas(str(pdf))
        for page in range(1, 3):
            text = c.beginText(50, 760)
            text.textLine("Results" if page == 2 else "Methods")
            for line in range(35):
                text.textLine(f"Page {page} hydrothermal sensor temperature observation number {line} provided reproducible evidence.")
            c.drawText(text); c.showPage()
        c.save()
        extracted = self.toolkit._extract_pdf(pdf, max_pages=10, max_ocr_pages=0)
        self.assertEqual(extracted["page_count"], 2)
        self.assertEqual([item["page"] for item in extracted["units"]], [1, 2])

    def test_schema_dispatch_and_manifest_builder(self):
        self.assertEqual({item["name"] for item in TOOL_SCHEMAS}, {"literature_full_text_status", "literature_full_text_evidence"})
        self.assertFalse(dispatch(self.toolkit, "unknown", {})["ok"])
        manifest = self.root / "tool_manifest.json"
        subprocess.run([os.environ.get("PYTHON", "python3"), str(Path(__file__).parent / "build_tool_manifest.py"), "--output", str(manifest)], check=True, capture_output=True)
        self.assertEqual(json.loads(manifest.read_text())["tools"], TOOL_SCHEMAS)


if __name__ == "__main__":
    unittest.main()
