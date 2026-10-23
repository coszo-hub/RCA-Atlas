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
        return [{"chunk_id": "c1", "collection_id": "axial_earthquakes", "collection_label": "axial_earthquakes", "title": "Axial", "text": "Evidence",
                 "score": .9, "lexical_score": .8, "vector_score": .95,
                 "citations": [{"source_id": "s1", "title": "Catalog", "url": "https://example.test"}],
                 "metadata": {"node_local_id": "e1", "locator": None}}]
    def neighbors(self, ids, **kwargs):
        self.calls.append(("neighbors", ids, kwargs))
        return [{"collection_id": "axial_earthquakes", "local_id": "e2", "name": "Station", "depth": 1,
                 "direction": "out", "predicate": "OBSERVES", "source_url": None}]
    def passages(self, query, embedding, **kwargs):
        self.calls.append(("passages", query, kwargs))
        return [{"chunk_id": "p1", "collection_id": "literature_fulltext", "collection_label": "literature_fulltext",
                 "title": "Paper", "text": "Passage", "score": .5, "lexical_score": .4, "vector_score": .5,
                 "citations": [{"source_id": "REF-1", "title": "Paper", "url": "https://doi.org/10.1/x"}],
                 "metadata": {"node_local_id": "p1", "locator": "page 3", "places": ["Oregon Slope Base"]}}]
    def papers_naming(self, terms, **kwargs):
        self.calls.append(("papers_naming", list(terms), kwargs))
        return [{"chunk_id": "p2", "collection_id": "literature_fulltext", "collection_label": "literature_fulltext",
                 "title": "Paper", "text": "AXEC2 recorded", "score": 3.0, "lexical_score": 0.0, "vector_score": 0.0,
                 "citations": [{"source_id": "REF-2", "title": "Paper", "url": "https://doi.org/10.1/y"}],
                 "metadata": {"node_local_id": "p2", "locator": "page 4", "places": [], "paper_key": "10.1/y",
                              "passages_naming": 3, "terms_named": ["AXEC2"]}}]
    def chunks_by_id(self, collection_id, chunk_ids):
        self.calls.append(("chunks_by_id", collection_id, list(chunk_ids)))
        return [{"chunk_id": chunk_ids[0], "collection_id": collection_id, "collection_label": collection_id,
                 "title": "BOTPT", "text": "Deployment 1", "score": 1.0, "lexical_score": 0.0, "vector_score": 0.0,
                 "citations": [{"source_id": "S", "title": "Deploy", "url": "https://github.com/x"}],
                 "metadata": {"node_local_id": chunk_ids[0], "locator": None, "places": []}}]
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

    def test_context_keeps_its_hits_when_the_graph_walk_times_out(self):
        def slow(ids, **kwargs):
            raise RuntimeError("canceling statement due to statement timeout")
        self.repo.neighbors = slow
        response = self.client.post("/v1/context", headers=self.headers, json={"query": "exact event count", "graph_hops": 2})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["hits"][0]["chunk_id"], "c1")
        self.assertEqual(response.json()["neighbors"], [])

    def test_papers_naming_takes_codes_only(self):
        response = self.client.post("/v1/papers-naming", headers=self.headers, json={"terms": ["AXEC1", "AXEC2"], "limit": 5})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["hits"][0]["metadata"]["terms_named"], ["AXEC2"])
        self.assertEqual(self.repo.calls[-1], ("papers_naming", ["AXEC1", "AXEC2"], {"limit": 5}))
        for bad in ({"terms": []}, {"terms": ["AX"]}, {"terms": ["x'); DROP"]}):
            self.assertEqual(self.client.post("/v1/papers-naming", headers=self.headers, json=bad).status_code, 422)

    def test_chunks_are_fetched_by_id_within_one_collection(self):
        ids = ["ooi_assets_RS03CCAL-MJ03F-05-BOTPTA301", "ooi_assets_depth_deeper_than_2000_m"]
        response = self.client.post("/v1/chunks", headers=self.headers, json={"collection_id": "ooi_asset_management", "chunk_ids": ids})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["hits"][0]["chunk_id"], ids[0])
        self.assertEqual(self.repo.calls[-1], ("chunks_by_id", "ooi_asset_management", ids))
        for bad in ({"collection_id": "ooi_asset_management", "chunk_ids": []},
                    {"collection_id": "Bad Collection", "chunk_ids": ["x_1"]},
                    {"collection_id": "ooi_asset_management", "chunk_ids": ["x'); DROP"]},
                    {"collection_id": "ooi_asset_management", "chunk_ids": [f"id_{i}" for i in range(13)]}):
            self.assertEqual(self.client.post("/v1/chunks", headers=self.headers, json=bad).status_code, 422)

    def test_passages_are_asked_within_the_named_papers(self):
        response = self.client.post("/v1/passages", headers=self.headers,
                                    json={"query": "which echosounder", "paper_keys": ["10.1/x", "REF-1"], "limit": 8})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["hits"][0]["metadata"]["places"], ["Oregon Slope Base"])
        self.assertEqual(self.repo.calls[-1], ("passages", "which echosounder", {"paper_keys": ["10.1/x", "REF-1"], "limit": 8}))
        self.assertEqual(self.client.post("/v1/passages", headers=self.headers, json={"query": "q?", "paper_keys": []}).status_code, 422)

    def test_bounds_and_unknown_fields(self):
        response = self.client.post("/v1/neighbors", headers=self.headers,
                                    json={"seeds": [{"collection_id": "axial_earthquakes", "local_id": "e1"}], "hops": 99})
        self.assertEqual(response.status_code, 422)
        response = self.client.post("/v1/tools", headers=self.headers,
                                    json={"query": "hi", "raw_sql": "select 1"})
        self.assertEqual(response.status_code, 422)


if __name__ == "__main__": unittest.main()
