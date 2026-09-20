import hashlib
import unittest

try:
    from fastapi.testclient import TestClient
    from app.config import Settings
    from app.main import create_app
except ImportError:  # permits discovery in minimal stdlib-only workspaces
    TestClient = None


class FakeEmbedding:
    dimensions = 384
    def embed_query(self, text):
        return [1.0] + [0.0] * 383


class FakeRepository:
    def __init__(self): self.calls = []
    def close(self): pass
    def health(self): return True
    def search(self, query, embedding, **kwargs):
        self.calls.append(("search", query, kwargs))
        return [{"chunk_id": "c1", "collection_id": "axial_earthquakes", "title": "Axial", "text": "Evidence",
                 "score": .9, "lexical_score": .8, "vector_score": .95,
                 "citations": [{"source_id": "s1", "title": "Catalog", "url": "https://example.test"}],
                 "metadata": {"node_local_id": "e1", "locator": None}}]
    def neighbors(self, ids, **kwargs):
        self.calls.append(("neighbors", ids, kwargs))
        return [{"collection_id": "axial_earthquakes", "local_id": "e2", "name": "Station", "depth": 1,
                 "direction": "out", "predicate": "OBSERVES", "source_url": None}]
    def route_tools(self, query, **kwargs):
        self.calls.append(("tools", query, kwargs))
        return [{"name": "count_events", "description": "Exact count", "score": .8,
                 "collection_id": "axial_earthquakes",
                 "required_arguments": ["day"], "input_schema": {"required": ["day"]}}]


@unittest.skipIf(TestClient is None, "install API dependencies")
class ApiTests(unittest.TestCase):
    def setUp(self):
        self.repo = FakeRepository()
        settings = Settings("postgresql://unused", frozenset({hashlib.sha256(b"secret").hexdigest()}))
        self.client = TestClient(create_app(settings=settings, repository=self.repo,
                                            embedding_provider=FakeEmbedding()))
        self.headers = {"X-API-Key": "secret"}

    def test_health_is_minimal_and_public(self):
        self.assertEqual(self.client.get("/health").json(), {"status": "ok"})

    def test_api_key_required(self):
        response = self.client.post("/v1/search", json={"query": "earthquakes"})
        self.assertEqual(response.status_code, 401)

    def test_search_returns_cited_evidence(self):
        response = self.client.post("/v1/search", headers=self.headers, json={"query": "earthquake counts"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["hits"][0]["citations"][0]["source_id"], "s1")

    def test_context_composes_search_graph_and_tools(self):
        response = self.client.post("/v1/context", headers=self.headers,
                                    json={"query": "exact event count", "graph_hops": 2})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["neighbors"][0]["local_id"], "e2")
        self.assertEqual(response.json()["tool_hints"][0]["name"], "count_events")

    def test_bounds_and_unknown_fields(self):
        response = self.client.post("/v1/neighbors", headers=self.headers,
                                    json={"seeds": [{"collection_id": "axial_earthquakes", "local_id": "e1"}], "hops": 99})
        self.assertEqual(response.status_code, 422)
        response = self.client.post("/v1/tools", headers=self.headers,
                                    json={"query": "hi", "raw_sql": "select 1"})
        self.assertEqual(response.status_code, 422)


if __name__ == "__main__": unittest.main()
