import tempfile
import unittest
from pathlib import Path

from datacloud_platform.pipeline_tools import deploy_check, retrieve_metadata


class PipelineToolsTests(unittest.TestCase):
    def test_retrieve_dry_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = retrieve_metadata(Path(tmp), "dev", "package.xml", dry_run=True)
            self.assertTrue(result["ok"])
            self.assertIn("Dry run", result["summary"])

    def test_deploy_check_dry_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = deploy_check(Path(tmp), "dev", "package.xml", dry_run=True)
            self.assertTrue(result["ok"])
            self.assertIn("Dry run", result["summary"])


if __name__ == "__main__":
    unittest.main()
