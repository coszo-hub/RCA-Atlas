import re
import unittest

from atlas_map_data import access, osu_axial


class OsuAxialTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.routes = osu_axial.load_figures()

    def test_each_botpt_and_seafloor_ctd_gets_its_own_page(self):
        self.assertEqual(len(self.routes), 8)
        for node in osu_axial.NODES.values():
            self.assertEqual(self.routes[node["botpt"]]["url"], osu_axial.BASE + node["page"])
        self.assertEqual(self.routes["RS03CCAL-MJ03F-12-CTDPFB305"]["url"], osu_axial.BASE + "CTD3.html")

    def test_the_refdes_table_matches_the_instrument_the_page_names(self):
        for refdes, route in self.routes.items():
            page = (osu_axial.SOURCE / route["url"].rsplit("/", 1)[1]).read_text(encoding="utf-8", errors="replace")
            title = re.search(r"<title>(.*?)</title>", page, re.S | re.I).group(1)
            node, cls = refdes.split("-")[1], refdes.split("-")[3]           # MJ03F, BOTPTA301 / CTDPFB305
            self.assertIn(node, title, refdes)
            if cls.startswith("CTD"):
                self.assertIn(cls, page, refdes)
            else:
                self.assertIn(f"BOTPT-{cls[5:]}-{node}", title, refdes)

    def test_figures_have_a_group_span_and_osu_url(self):
        central = self.routes["RS03CCAL-MJ03F-05-BOTPTA301"]["figures"]
        first = central[0]
        self.assertEqual((first["group"], first["span"]), ("Depth (de-tided pressure)", "7 days"))
        self.assertEqual(first["url"], "https://axial.ceoas.oregonstate.edu/graphs/MJ03F7DaysDET.png")
        self.assertTrue(first["caption"].startswith("NANO-BPR pressure data with predicted tides removed"))
        self.assertNotIn("ONLY UPDATED", " ".join(f["caption"] for f in central))
        every = [f for r in self.routes.values() for f in r["figures"]]
        self.assertEqual([f["url"] for f in every if not f["caption"]], [])     # each figure keeps OSU's caption
        diff = next(f for f in central if f["url"].endswith("NANOdifferenceLast7DaysE-F.png"))
        self.assertEqual(diff["caption"], "Depth-difference (MJ03E-MJ03F), last 7 days.")
        groups = {f["group"] for f in central}
        self.assertTrue({"Uplift rate", "Tilt rate", "Event alarms", "Differential uplift, Eastern minus Central"} <= groups)
        # A figure belongs to one instrument, except the E-F difference and the alarm table of all four.
        ashes = {f["url"] for f in self.routes["RS03ASHS-MJ03B-09-BOTPTA304"]["figures"]}
        self.assertFalse(any("MJ03F" in u for u in ashes))
        self.assertIn(osu_axial.BASE + "graphs/AlarmSummary.png", ashes)
        self.assertFalse(any("NANOdifference" in u for u in ashes))
        for r in self.routes.values():
            pairs = [(f["group"], f["span"]) for f in r["figures"]]
            self.assertEqual(len(pairs), len(set(pairs)))      # one figure per group and span

    def test_access_offers_the_route_on_osus_host(self):
        ext = {"erddap": set(), "qaqc": set(), "warnings": [], "osu_axial": self.routes}
        routes = access.build_access({"id": "X", "instrumentId": "I", "refdes": "RS03CCAL-MJ03F-12-CTDPFB305", "sources": []}, ext, {}, {})
        osu = [r for r in routes if r["kind"] == "osu_axial"]
        self.assertEqual(osu[0]["url"], "https://axial.ceoas.oregonstate.edu/CTD3.html")
        self.assertEqual(len(osu[0]["figures"]), 9)


if __name__ == "__main__":
    unittest.main()
