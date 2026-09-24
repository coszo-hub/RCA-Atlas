import dataclasses
import json
import unittest

import httpx
from fastapi.testclient import TestClient

from atlas_map_gateway.app import create_app
from atlas_map_gateway.main import make_chat
from atlas_map_gateway.tests.fakes import SETTINGS, deps


class ChatTest(unittest.TestCase):
    def test_proxy_sends_key_and_trims_response(self):
        seen = {}

        def handler(req: httpx.Request):
            seen["url"], seen["key"], seen["body"] = str(req.url), req.headers.get("x-api-key"), req.read()
            return httpx.Response(200, json={"answer": "Axial has 66 sensors.", "answer_model": "gemini-2.5-flash",
                                             "answer_citations": [{"id": "c1", "title": "OOI", "url": "https://oceanobservatories.org"}],
                                             "hits": [{"huge": "payload"}]})
        chat = make_chat(SETTINGS, httpx.Client(transport=httpx.MockTransport(handler)))
        r = TestClient(create_app(SETTINGS, deps(chat=chat))).post("/chat", json={"question": "What is at Axial?"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"answer": "Axial has 66 sensors.", "model": "gemini-2.5-flash",
                                    "citations": [{"id": "c1", "title": "OOI", "url": "https://oceanobservatories.org"}]})
        self.assertEqual(seen["url"], "http://graphrag.test/v1/answer")
        self.assertEqual(seen["key"], "k")
        self.assertEqual(json.loads(seen["body"])["query"], "What is at Axial?")

    def test_empty_question_422(self):
        r = TestClient(create_app(SETTINGS, deps(chat=lambda q: {}))).post("/chat", json={"question": " "})
        self.assertEqual(r.status_code, 422)

    def test_upstream_down_502(self):
        def handler(req):
            return httpx.Response(503, json={"detail": "answer model is not configured"})
        chat = make_chat(SETTINGS, httpx.Client(transport=httpx.MockTransport(handler)))
        r = TestClient(create_app(SETTINGS, deps(chat=chat))).post("/chat", json={"question": "hello there"})
        self.assertEqual(r.status_code, 502)
        self.assertEqual(r.json()["error"]["source"], "Atlas chat")

    def test_whitespace_or_oversized_question_422_without_upstream_call(self):
        calls = []
        app = create_app(SETTINGS, deps(chat=lambda q: calls.append(q) or {}))
        for question in ("     ", "x" * 1001):
            with self.subTest(length=len(question)):
                r = TestClient(app).post("/chat", json={"question": question})
                self.assertEqual(r.status_code, 422)
                self.assertEqual(r.json()["error"]["source"], "atlas")
        self.assertEqual(calls, [])

    def test_question_is_stripped(self):
        calls = []
        app = create_app(SETTINGS, deps(chat=lambda q: calls.append(q) or {"answer": "", "model": None, "citations": []}))
        r = TestClient(app).post("/chat", json={"question": "  What is at Axial?  "})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(calls, ["What is at Axial?"])

    def test_timeout_504(self):
        def handler(req):
            raise httpx.ReadTimeout("slow", request=req)
        chat = make_chat(SETTINGS, httpx.Client(transport=httpx.MockTransport(handler)))
        r = TestClient(create_app(SETTINGS, deps(chat=chat))).post("/chat", json={"question": "hello there"})
        self.assertEqual(r.status_code, 504)
        self.assertEqual(r.json()["error"]["source"], "Atlas chat")

    def test_busy_limiter_is_503_with_display_source(self):
        busy = dataclasses.replace(SETTINGS, per_host_limit=1, upstream_timeout=0.01)
        app = create_app(busy, deps(chat=lambda q: {}))
        with app.state.limiter.slot("Atlas chat"):
            r = TestClient(app).post("/chat", json={"question": "hello there"})
        self.assertEqual(r.status_code, 503)
        self.assertEqual(r.json()["error"]["source"], "Atlas chat")


if __name__ == "__main__":
    unittest.main()
