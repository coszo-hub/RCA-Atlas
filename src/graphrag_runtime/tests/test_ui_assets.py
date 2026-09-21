from pathlib import Path
import unittest


class WorkspaceAssetTests(unittest.TestCase):
    def test_workspace_assets_are_versioned_and_do_not_embed_secrets(self):
        static_root = Path(__file__).resolve().parents[1] / "app" / "static"
        index = (static_root / "index.html").read_text(encoding="utf-8")
        script = (static_root / "atlas.js").read_text(encoding="utf-8")
        self.assertIn("RCA Atlas", index)
        self.assertIn("/v1/context", script)
        self.assertNotIn("localStorage", script)
        self.assertNotIn("GRAPHRAG_API_KEY=", index + script)


if __name__ == "__main__":
    unittest.main()
