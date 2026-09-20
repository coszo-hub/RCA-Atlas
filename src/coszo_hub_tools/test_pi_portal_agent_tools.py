import json
import os
import tempfile
import unittest
from pathlib import Path
from urllib.error import URLError

from pi_portal_agent_tools import PI_INSTRUMENTS, PIPortalToolkit, dispatch_pi_portal


class FakePIPortalHTTP:
    def __init__(self):
        self.calls = []

    def __call__(self, *, url, max_bytes):
        self.calls.append({"url": url, "max_bytes": max_bytes})
        pages = {
            "http://piweb.ooirsn.uw.edu/marum/data/CTDPFA110/": """
                <html><a href='../'>Parent Directory</a><a href='2025/'>2025/</a>
                <a href='2026/'>2026/</a><a href='?C=N;O=D'>Name</a></html>""",
            "http://piweb.ooirsn.uw.edu/marum/data/CTDPFA110/2025/":
                "<html><a href='09/'>09/</a></html>",
            "http://piweb.ooirsn.uw.edu/marum/data/CTDPFA110/2025/09/":
                "<html><a href='2025-09-19.dat'>2025-09-19.dat</a></html>",
            "http://piweb.ooirsn.uw.edu/marum/data/CTDPFA110/2026/":
                "<html><a href='09/'>09/</a></html>",
            "http://piweb.ooirsn.uw.edu/marum/data/CTDPFA110/2026/09/": """
                <html><a href='2026-09-18.dat'>2026-09-18.dat</a>
                <a href='2026-09-19.dat'>2026-09-19.dat</a></html>""",
        }
        if url in pages:
            return 200, {"Content-Type": "text/html"}, pages[url].encode(), url
        if url.endswith(".dat"):
            return 200, {"Content-Type": "application/octet-stream"}, ("DATA:" + url).encode(), url
        return 404, {"Content-Type": "text/plain"}, b"not found", url


class PIPortalToolkitTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.http = FakePIPortalHTTP()
        self.toolkit = PIPortalToolkit(runtime_root=Path(self.temp.name) / "PIPortal", http_get=self.http)
        self.toolkit.retry_backoff_seconds = 0

    def tearDown(self):
        self.temp.cleanup()

    def test_registry_has_ten_graph_ready_datasets_and_offline_status(self):
        status = self.toolkit.status()
        self.assertEqual(status["dataset_count"], 10)
        self.assertFalse(status["credentials_required"])
        self.assertIn("Graph-RAG", status["workflow"])
        listed = self.toolkit.list_instruments("pressure")
        self.assertGreaterEqual(listed["count"], 2)
        self.assertEqual(self.http.calls, [])
        for key, instrument in PI_INSTRUMENTS.items():
            self.assertEqual(instrument["canonical_id"], key)
            self.assertTrue(instrument["official_url"].startswith("https://"))
            self.assertTrue(instrument["endpoints"])
            self.assertIn("base_url", instrument["endpoints"][0])

    def test_multiple_endpoint_dataset_requires_explicit_endpoint(self):
        result = dispatch_pi_portal(self.toolkit, "pi_portal_browse", {"instrument_id": "PI-DAS25"})
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["type"], "ValueError")

    def test_browse_parses_only_in_endpoint_links(self):
        result = self.toolkit.browse("PI-CTDPFA110")
        self.assertTrue(result["ok"])
        self.assertEqual([item["relative_path"] for item in result["entries"]], ["2025/", "2026/"])
        self.assertTrue(all(item["kind"] == "directory" for item in result["entries"]))

    def test_recursive_find_filters_extension_and_date(self):
        result = self.toolkit.find_files(
            "PI-CTDPFA110", extensions=["dat"], start="2026-09-19", end="2026-09-19",
            max_depth=2, max_directories=10, max_files=10,
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["files"][0]["relative_path"], "2026/09/2026-09-19.dat")
        self.assertEqual(result["files"][0]["observation_date"], "2026-09-19")

    def test_plan_is_offline_and_rejects_path_escape(self):
        plan = self.toolkit.plan_download("PI-CTDPFA110", ["2026/09/2026-09-19.dat"])
        self.assertFalse(plan["live_request_executed"])
        self.assertEqual(self.http.calls, [])
        for bad in ("../secret", "%2e%2e/secret", "/etc/passwd", "2026//file.dat", "https://evil.example/file"):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    self.toolkit.plan_download("PI-CTDPFA110", [bad])

    def test_exact_host_guard_rejects_lookalikes_and_credentials(self):
        for url in (
            "http://piweb.ooirsn.uw.edu.evil.example/data/",
            "http://user:pass@piweb.ooirsn.uw.edu/data/",
            "http://piweb.ooirsn.uw.edu:8080/data/",
            "ftp://piweb.ooirsn.uw.edu/data/",
        ):
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    self.toolkit._approved_url(url)

        def redirected(**kwargs):
            return 200, {}, b"bad", "http://evil.example/stolen"

        redirected_toolkit = PIPortalToolkit(runtime_root=Path(self.temp.name) / "redirect", http_get=redirected)
        with self.assertRaises(ValueError):
            redirected_toolkit._http("http://piweb.ooirsn.uw.edu/a0a/", 1024)

    def test_transient_connection_failure_is_retried(self):
        calls = []

        def flaky(*, url, max_bytes):
            calls.append(url)
            if len(calls) == 1:
                raise URLError("connection refused")
            return 200, {"Content-Type": "text/html"}, b"<html></html>", url

        toolkit = PIPortalToolkit(runtime_root=Path(self.temp.name) / "retry", http_get=flaky)
        toolkit.retry_backoff_seconds = 0
        toolkit.max_retries = 2
        result = toolkit.browse("PI-CTDPFA110")
        self.assertTrue(result["ok"])
        self.assertEqual(len(calls), 2)

    def test_unfiltered_covis_raw_search_is_rejected(self):
        result = dispatch_pi_portal(self.toolkit, "pi_portal_find_files", {
            "instrument_id": "PI-COVIS", "endpoint_id": "covis-raw",
        })
        self.assertFalse(result["ok"])
        self.assertIn("large flat archive", result["error"]["message"])
        self.assertEqual(self.http.calls, [])

    def test_download_writes_hashes_and_private_manifest(self):
        result = self.toolkit.download_files("PI-CTDPFA110", [
            "2026/09/2026-09-18.dat", "2026/09/2026-09-19.dat",
        ])
        self.assertTrue(result["ok"])
        self.assertEqual(result["file_count"], 2)
        self.assertFalse(result["credential_used"])
        manifest_path = Path(result["manifest"])
        manifest = json.loads(manifest_path.read_text())
        self.assertEqual(manifest["local_request_id"], result["local_request_id"])
        self.assertEqual(len(manifest["files"][0]["sha256"]), 64)
        self.assertTrue(all(Path(item["file"]).is_file() for item in manifest["files"]))
        if os.name == "posix":
            self.assertEqual(manifest_path.stat().st_mode & 0o777, 0o600)

    def test_download_total_byte_limit_is_enforced(self):
        self.toolkit.max_download_bytes = 8
        result = dispatch_pi_portal(self.toolkit, "pi_portal_download_files", {
            "instrument_id": "PI-CTDPFA110", "relative_paths": ["2026/09/2026-09-19.dat"],
        })
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["type"], "PIPortalError")


if __name__ == "__main__":
    unittest.main()
