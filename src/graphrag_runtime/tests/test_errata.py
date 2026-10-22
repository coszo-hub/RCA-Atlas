import json
import tempfile
import unittest
from pathlib import Path

from normalize_corpus import apply_errata, load_errata

ENTRY = {"chunk_id": "W-1", "wrong": "spaced 400-500 m apart", "right": "spaced 300–450 m apart",
         "authority": {"title": "Stacked sills", "doi": "10.1130/g47223.1"}, "reason": "The paper gives 300–450 m."}


class ErrataTest(unittest.TestCase):
    def test_the_paper_corrects_the_website_text_and_the_record_says_so(self):
        fixed = apply_errata({"chunk_id": "W-1", "text": "Lenses spaced 400-500 m apart."}, [ENTRY], "websites/W-1")
        self.assertEqual(fixed["text"], "Lenses spaced 300–450 m apart.")
        self.assertEqual(fixed["errata"][0]["authority"]["doi"], "10.1130/g47223.1")

    def test_a_stale_erratum_stops_the_build(self):
        with self.assertRaisesRegex(ValueError, "exactly once"):
            apply_errata({"text": "The page was rewritten."}, [ENTRY], "websites/W-1")

    def test_errata_load_from_the_collection_auxiliary_file(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "data").mkdir()
            (Path(d) / "data" / "errata.jsonl").write_text(json.dumps(ENTRY) + "\n")
            errata = load_errata(Path(d), {"auxiliary_inputs": [{"path": "data/errata.jsonl"}]})
        self.assertEqual(list(errata), ["W-1"])

    def test_the_committed_website_errata_match_their_chunks(self):
        root = Path(__file__).resolve().parents[3]
        chunks = {json.loads(l)["chunk_id"]: json.loads(l) for l in (root / "data/Websites/chunks.jsonl").open()}
        for line in (root / "data/Websites/errata.jsonl").open():
            e = json.loads(line)
            apply_errata(chunks[e["chunk_id"]], [e], e["chunk_id"])     # raises if the page text moved


if __name__ == "__main__":
    unittest.main()
