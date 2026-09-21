from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from model_eval.costs import Price, cost_report, estimate_cost
from model_eval.embeddings import HTTPEmbeddingProvider, IndexSpec, load_index_specs
from model_eval.metrics import ndcg_at, recall_at, reciprocal_rank
from model_eval.orchestrator import GraphRAGOrchestrator
from model_eval.providers import (AnthropicProvider, GeminiProvider, OpenAICompatibleProvider,
                                  OpenAIResponsesProvider, ProviderError)
from model_eval.retrieval import RankedCandidate, graph_expand, reciprocal_rank_fusion, route_query
from model_eval.runner import QueryCache, dry_run_estimate, evaluation_record
from model_eval.schemas import AnswerRequest, EvidenceItem, EvidencePackage, ModelResponse, Usage


ROOT = Path(__file__).resolve().parents[1]


def evidence() -> EvidencePackage:
    return EvidencePackage("ev-1", "corpus-1", "graph-1", "Where is PREST data?", (
        EvidenceItem("chunk:prest", "chunk", "PREST data are available through OOI M2M.", "https://example.test/prest"),
    ), ("instrument:PREST",), ("instrument:PREST|DOWNLOADABLE_FROM|service:OOI_M2M",))


class MockProvider:
    def answer(self, request):
        return ModelResponse("mock", "mock-1", "mock-1.0", "OOI M2M [chunk:prest]", ("chunk:prest",),
                             usage=Usage(100, 10))


class MockRetriever:
    def retrieve(self, question):
        return evidence()


class ModelLabTests(unittest.TestCase):
    def test_dataset_has_representative_unique_questions(self):
        rows = [json.loads(line) for line in (ROOT / "datasets/rca_eval_v1.jsonl").read_text().splitlines()]
        self.assertGreaterEqual(len(rows), 50)
        self.assertLessEqual(len(rows), 100)
        self.assertEqual(len(rows), len({row["id"] for row in rows}))
        self.assertTrue({"instrument_identity", "chronfix", "visual", "tool_selection", "full_text"}
                        <= {row["category"] for row in rows})

    def test_gold_dataset_covers_every_question_without_duplicates(self):
        questions = [json.loads(line) for line in (ROOT / "datasets/rca_eval_v1.jsonl").read_text().splitlines()]
        gold = [json.loads(line) for line in (ROOT / "datasets/rca_eval_v1_gold.jsonl").read_text().splitlines()]
        self.assertEqual({row["id"] for row in questions}, {row["question_id"] for row in gold})
        self.assertEqual(len(gold), len({row["question_id"] for row in gold}))
        self.assertTrue(all(row.get("reference_answer") for row in gold))
        self.assertTrue(all(row["review_status"] in {"corpus_verified", "requires_human_review"} for row in gold))

    def test_query_routing_is_selective(self):
        self.assertNotIn("visual", route_query("Where is PREST deployed?"))
        self.assertIn("visual", route_query("Show a figure of PN1B"))
        self.assertIn("scientific", route_query("Find publications about Axial"))

    def test_rrf_is_stable_and_independent(self):
        left = [RankedCandidate("a", 1, "text", {}), RankedCandidate("b", 2, "text", {})]
        right = [RankedCandidate("b", 1, "keyword", {}), RankedCandidate("c", 2, "keyword", {})]
        fused = reciprocal_rank_fusion([left, right])
        self.assertEqual(fused[0][0], "b")
        self.assertEqual({row[0] for row in fused}, {"a", "b", "c"})

    def test_graph_expansion_is_bounded(self):
        graph = {"a": [("P1", "b")], "b": [("P2", "c")], "c": [("P3", "d")]}
        self.assertEqual(len(graph_expand(["a"], graph, hops=2)), 2)
        self.assertEqual(len(graph_expand(["a"], graph, hops=99)), 3)

    def test_retrieval_metrics(self):
        retrieved, relevant = ["x", "a", "b"], {"a", "b"}
        self.assertEqual(recall_at(retrieved, relevant, 2), 0.5)
        self.assertEqual(reciprocal_rank(retrieved, relevant), 0.5)
        self.assertGreater(ndcg_at(retrieved, {"a": 2, "b": 1}, 3), 0)

    def test_cost_estimate_and_dry_run_send_nothing(self):
        price = Price(4, 20, 0.4)
        self.assertAlmostEqual(estimate_cost(Usage(1000, 100, 500), price), 0.0042)
        report = dry_run_estimate([{"id": "q"}], ["m"], {"m": price}, evidence_tokens=1000, output_tokens=100)
        self.assertEqual(report["network_requests_sent"], 0)

    def test_query_cache_is_content_addressed(self):
        with tempfile.TemporaryDirectory() as temp:
            cache = QueryCache(Path(temp))
            cache.put("answers", {"q": "one"}, {"answer": 1})
            self.assertEqual(cache.get("answers", {"q": "one"}), {"answer": 1})
            self.assertIsNone(cache.get("answers", {"q": "two"}))

    def test_openai_contract(self):
        seen = {}
        def transport(url, headers, payload, timeout):
            seen.update(url=url, headers=headers, payload=payload)
            return {"id": "r1", "model": "gpt-exact", "output_text": "answer", "usage": {"input_tokens": 4, "output_tokens": 2}}
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test"}):
            response = OpenAIResponsesProvider("gpt-test", transport=transport).answer(
                AnswerRequest("q", "question", evidence()))
        self.assertTrue(seen["url"].endswith("/responses"))
        self.assertEqual(response.exact_model_version, "gpt-exact")

    def test_anthropic_contract(self):
        def transport(url, headers, payload, timeout):
            self.assertEqual(headers["anthropic-version"], "2023-06-01")
            return {"id": "a1", "model": "claude-exact", "content": [{"type": "text", "text": "answer"}],
                    "usage": {"input_tokens": 3, "output_tokens": 1}}
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test"}):
            response = AnthropicProvider("claude-test", transport=transport).answer(
                AnswerRequest("q", "question", evidence()))
        self.assertEqual(response.answer, "answer")

    def test_gemini_contract(self):
        def transport(url, headers, payload, timeout):
            self.assertIn(":generateContent", url)
            return {"modelVersion": "gemini-exact", "candidates": [{"content": {"parts": [{"text": "answer"}]}}],
                    "usageMetadata": {"promptTokenCount": 3, "candidatesTokenCount": 2}}
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test"}):
            response = GeminiProvider("gemini-test", transport=transport).answer(
                AnswerRequest("q", "question", evidence()))
        self.assertEqual(response.usage.output_tokens, 2)

    def test_openai_compatible_contract_without_local_key(self):
        def transport(url, headers, payload, timeout):
            return {"model": "qwen-local", "choices": [{"message": {"content": "answer"}}], "usage": {}}
        response = OpenAICompatibleProvider("qwen", base_url="http://localhost:8001/v1", transport=transport).answer(
            AnswerRequest("q", "question", evidence()))
        self.assertEqual(response.answer, "answer")

    def test_provider_missing_key_fails_closed(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ProviderError, "OPENAI_API_KEY"):
                OpenAIResponsesProvider("gpt-test").answer(AnswerRequest("q", "question", evidence()))

    def test_embedding_contract(self):
        spec = IndexSpec("test", "embed", "openai_compatible", 3, ("text",), "v1", base_url="http://local")
        def transport(url, headers, payload, timeout):
            return {"data": [{"embedding": [1, 0, 0]}, {"embedding": [0, 1, 0]}]}
        self.assertEqual(HTTPEmbeddingProvider(spec, transport=transport).embed(["a", "b"], input_type="document")[1], [0.0, 1.0, 0.0])

    def test_embedding_registry_keeps_bge_and_content_indexes(self):
        specs = load_index_specs(ROOT / "config/embedding_indexes.json")
        self.assertEqual(specs["local_bge_small"].status, "production")
        self.assertTrue(any("visual" in spec.content_types for spec in specs.values()))
        self.assertTrue(any("scientific" in spec.content_types for spec in specs.values()))

    def test_complete_corpus_only_graphrag_flow_avoids_tool(self):
        response = GraphRAGOrchestrator(MockRetriever(), MockProvider()).answer("q", "Where is PREST data?")
        self.assertIn("chunk:prest", response.answer)
        self.assertEqual(response.tool_calls, ())

    def test_evaluation_record_has_required_provenance(self):
        response = MockProvider().answer(AnswerRequest("q", "question", evidence()))
        record = evaluation_record({"id": "q"}, evidence(), response, embedding_model="bge", index_version="v1", prompt_version="p1")
        for key in ("question_id", "corpus_version", "graph_version", "retrieved_chunk_ids", "retrieved_graph_edges",
                    "answer_model_exact_version", "prompt_version", "input_tokens", "estimated_cost_usd"):
            self.assertIn(key, record)

    def test_monthly_cost_report_groups_models(self):
        report = cost_report([{"answer_model": "a", "estimated_cost_usd": 1},
                              {"answer_model": "a", "estimated_cost_usd": 2}])
        self.assertEqual(report["by_model"]["a"]["runs"], 2)
        self.assertEqual(report["total_estimated_cost_usd"], 3)


if __name__ == "__main__":
    unittest.main()
