import tempfile
import threading
import unittest
from pathlib import Path

from atlas_map_gateway import bundle_index, cache, config, errors

FIX = Path(__file__).parent / "fixtures" / "bundle"


class SettingsTest(unittest.TestCase):
    def test_dotenv_and_env_precedence(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / ".env"
            p.write_text("GRAPHRAG_API_KEY=from-dotenv\nGRAPHRAG_API_PORT=18000\n# comment\nBAD LINE\n")
            s = config.load_settings(env={}, dotenv=p)
            self.assertEqual(s.api_key, "from-dotenv")
            self.assertEqual(s.api_url, "http://127.0.0.1:18000")
            s2 = config.load_settings(env={"ATLAS_API_KEY": "explicit", "ATLAS_API_URL": "http://x:1"}, dotenv=p)
            self.assertEqual((s2.api_key, s2.api_url), ("explicit", "http://x:1"))

    def test_defaults_match_spec(self):
        s = config.load_settings(env={}, dotenv=Path("/nonexistent"))
        self.assertEqual((s.upstream_timeout, s.chat_timeout, s.max_series_days, s.max_waveform_minutes, s.max_points, s.per_host_limit),
                         (8.0, 60.0, 31, 60, 2000, 4))


class BundleIndexTest(unittest.TestCase):
    def setUp(self):
        self.ix = bundle_index.BundleIndex.from_dir(FIX)

    def test_lookups(self):
        self.assertTrue(self.ix.has_refdes("RS03AXPS-PC03A-4A-CTDPFA303"))
        self.assertFalse(self.ix.has_refdes("RS99XXXX-XX000-00-NOPE00000"))
        self.assertEqual(self.ix.erddap_dataset("RS03AXPS-PC03A-4A-CTDPFA303"), "ooi-rs03axps-pc03a-4a-ctdpfa303")
        self.assertIsNone(self.ix.erddap_dataset("RS01SBPD-DP01A-01-CTDPFL104"))
        self.assertEqual(self.ix.station("OO", "AXCC1"), {"channel": "HHZ"})
        self.assertIsNone(self.ix.station("OO", "NOPE"))
        self.assertTrue(self.ix.has_pi("PI-COVIS"))
        self.assertFalse(self.ix.has_pi("PI-NOPE"))


class CacheTest(unittest.TestCase):
    def test_caches_success_until_ttl(self):
        now = [0.0]
        c = cache.TTLCache(clock=lambda: now[0])
        calls = []
        fn = lambda: calls.append(1) or len(calls)
        self.assertEqual(c.get_or_set("k", 10, fn), 1)
        self.assertEqual(c.get_or_set("k", 10, fn), 1)
        now[0] = 11
        self.assertEqual(c.get_or_set("k", 10, fn), 2)

    def test_failures_are_not_cached(self):
        c = cache.TTLCache()
        def boom():
            raise errors.UpstreamError("ERDDAP", "down")
        with self.assertRaises(errors.UpstreamError):
            c.get_or_set("k", 10, boom)
        self.assertEqual(c.get_or_set("k", 10, lambda: "ok"), "ok")


class LimiterTest(unittest.TestCase):
    def test_limit_and_busy(self):
        lim = cache.HostLimiter(limit=1, wait=0.05)
        entered = threading.Event()
        release = threading.Event()
        def hold():
            with lim.slot("nereus"):
                entered.set()
                release.wait(1)
        t = threading.Thread(target=hold)
        t.start()
        entered.wait(1)
        with self.assertRaises(errors.Busy):
            with lim.slot("nereus"):
                pass
        with lim.slot("erddap"):   # other sources are independent
            pass
        release.set()
        t.join()


if __name__ == "__main__":
    unittest.main()
