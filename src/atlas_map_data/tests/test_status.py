import unittest

from atlas_map_data import status

ENTITIES = [
    {"entity_type": "instrument", "reference_designator": "RS03CCAL-MJ03F-05-BOTPTA301",
     "operational_status": "OPERATIONAL", "retrieved_at": "2026-09-19T07:41:44+00:00"},
    {"entity_type": "instrument", "reference_designator": "RS01SBPD-DP01A-00-ENG000000",
     "operational_status": "NOT_DEPLOYED", "retrieved_at": "2026-09-19T07:41:44+00:00"},
    {"entity_type": "deployment", "deployment_id": 1},
]
CROSSWALK = [
    {"reference_designator": "RS03CCAL-MJ03F-05-BOTPTA301", "instrument_graph_id": "INSTRUMENT-1",
     "match_type": "exact_reference_designator"},
    {"reference_designator": "RS01SBPD-DP01A-00-ENG000000", "instrument_graph_id": None,
     "match_type": "not_present_in_current_instrument_graph"},
]


class StatusTest(unittest.TestCase):
    def setUp(self):
        self.index = status.load_status_index(ENTITIES, CROSSWALK)

    def test_index_uses_exact_crosswalk_matches_only(self):
        self.assertEqual(set(self.index), {"INSTRUMENT-1"})
        self.assertEqual(self.index["INSTRUMENT-1"]["status"], "OPERATIONAL")

    def test_nereus_status_wins(self):
        r = status.resolve({"instrumentId": "INSTRUMENT-1", "coszoRole": "new_sensor_suite"}, self.index)
        self.assertEqual(r, {"status": "OPERATIONAL", "statusSource": "Nereus snapshot",
                             "statusAsOf": "2026-09-19T07:41:44+00:00"})

    def test_new_coszo_suites_are_planned(self):
        for role in ("new_sensor_suite", "Oregon_Shelf_suite"):
            r = status.resolve({"instrumentId": "INSTRUMENT-9", "coszoRole": role}, self.index)
            self.assertEqual(r["status"], "PLANNED")
            self.assertEqual(r["statusSource"], "Inventory: new COSZO sensor")

    def test_everything_else_is_unknown(self):
        for role in (None, "existing_RCA_foundation", "related_deployment_site_asset"):
            r = status.resolve({"instrumentId": "INSTRUMENT-9", "coszoRole": role}, self.index)
            self.assertEqual(r, {"status": "UNKNOWN", "statusSource": None, "statusAsOf": None})

    def test_every_raw_status_has_a_group(self):
        for raw in ("OPERATIONAL", "PARTIALLY_FUNCTIONAL", "NOT_DEPLOYED", "RETIRED", "SUPERSEDED",
                    "RECOVERED", "UNCABLED", "PLANNED", "UNKNOWN"):
            self.assertIn(status.STATUS_GROUP[raw], {"operating", "offline", "planned", "unknown"})


if __name__ == "__main__":
    unittest.main()
