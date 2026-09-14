import csv
import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

from src.photo_system_automation import font_audit_command, load_font_catalog


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class FontCatalogTests(unittest.TestCase):
    def test_catalog_is_fully_triaged(self):
        rows = load_font_catalog(PROJECT_ROOT / "data/font-licensing-audit.csv")
        self.assertEqual(2_195, len(rows))
        statuses = {row["status"] for row in rows}
        self.assertNotIn("unknown", statuses)
        self.assertNotIn("documentation_only_review", statuses)
        self.assertNotIn("commercial_evidence_review", statuses)

    def test_empty_intake_is_clean(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            intake = root / "_Incoming"
            intake.mkdir()
            reports = root / "reports"
            config = root / "config.json"
            config.write_text(
                json.dumps(
                    {
                        "font_library_root": str(root),
                        "font_intake": str(intake),
                        "font_reports_root": str(reports),
                        "font_catalog": str(PROJECT_ROOT / "data/font-licensing-audit.csv"),
                    }
                )
            )
            status = font_audit_command(Namespace(config=config, notify=False))
            self.assertEqual(0, status)
            report = sorted(reports.glob("*.json"))[-1]
            payload = json.loads(report.read_text())
            self.assertEqual(0, payload["file_count"])
            self.assertEqual(0, payload["issue_count"])


if __name__ == "__main__":
    unittest.main()
