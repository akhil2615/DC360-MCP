import tempfile
import unittest
from pathlib import Path

from datacloud_platform.blueprint_tools import generate_blueprint_artifacts


class BlueprintToolsTests(unittest.TestCase):
    def test_generate_blueprint_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            metadata = root / "metadata"
            output = root / "out"
            metadata.mkdir(parents=True, exist_ok=True)

            sample = metadata / "SampleDataStream-meta.xml"
            sample.write_text("<root><name>sample</name></root>", encoding="utf-8")

            result = generate_blueprint_artifacts(metadata, output, "TestBrand")
            self.assertTrue(result["ok"])
            details = result["details"]
            self.assertTrue(Path(details["json_path"]).exists())
            self.assertTrue(Path(details["html_path"]).exists())


if __name__ == "__main__":
    unittest.main()
