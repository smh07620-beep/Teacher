from pathlib import Path
import importlib.util
import json
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


def _load_module():
    path = ROOT / "tools" / "lighthouse_summary.py"
    spec = importlib.util.spec_from_file_location("lighthouse_summary_under_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _report(url, perf, a11y, bp, lcp, cls, tbt, form_factor="desktop"):
    return {
        "finalUrl": url,
        "configSettings": {"formFactor": form_factor},
        "categories": {
            "performance": {"score": perf},
            "accessibility": {"score": a11y},
            "best-practices": {"score": bp},
        },
        "audits": {
            "largest-contentful-paint": {"numericValue": lcp},
            "cumulative-layout-shift": {"numericValue": cls},
            "total-blocking-time": {"numericValue": tbt},
        },
    }


class LighthouseSummaryTests(unittest.TestCase):
    def setUp(self):
        self.module = _load_module()

    def _write_reports(self, directory: Path, reports, manifest_extra=None):
        manifest = []
        for index, report in enumerate(reports):
            path = directory / f"run-{index}.report.json"
            path.write_text(json.dumps(report), encoding="utf-8")
            entry = {"url": report["finalUrl"], "isRepresentativeRun": True, "jsonPath": str(path)}
            manifest.append(entry)
        manifest.extend(manifest_extra or [])
        (directory / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    def test_table_marks_passing_and_failing_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            self._write_reports(
                directory,
                [
                    _report("https://example.test/", 0.95, 0.96, 1.0, 1500, 0.0, 0),
                    _report("https://example.test/pgy", 0.5, 0.85, 0.79, 6000, 0.2, 900),
                ],
            )
            text = self.module.build_summary(directory, title="電腦版", base_url="https://example.test")
        self.assertIn("### 電腦版", text)
        self.assertIn("電腦版", text)
        self.assertIn("| `/` | 🟢 95 | 🟢 96 | 🟢 100 | 🟢 1.5 秒 | 🟢 0.000 | 🟢 0 ms |", text)
        self.assertIn("| `/pgy` | 🟠 50 | 🟠 85 | 🟠 79 | 🟠 6.0 秒 | 🟠 0.200 | 🟠 900 ms |", text)

    def test_only_representative_run_is_listed(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            extra_path = directory / "extra.report.json"
            extra_path.write_text(json.dumps(_report("https://example.test/extra", 1, 1, 1, 1, 0, 0)), encoding="utf-8")
            self._write_reports(
                directory,
                [_report("https://example.test/", 0.9, 0.9, 0.9, 1000, 0, 0)],
                manifest_extra=[{"url": "x", "isRepresentativeRun": False, "jsonPath": str(extra_path)}],
            )
            text = self.module.build_summary(directory, base_url="https://example.test")
        self.assertIn("`/`", text)
        self.assertNotIn("/extra", text)

    def test_mobile_label(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            self._write_reports(
                directory,
                [_report("https://example.test/login", 0.9, 0.9, 0.9, 1000, 0, 0, form_factor="mobile")],
            )
            text = self.module.build_summary(directory)
        self.assertIn("手機版", text)

    def test_missing_manifest_is_explained_not_raised(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = self.module.build_summary(Path(tmp), title="手機版")
        self.assertIn("沒有找到 Lighthouse 報告", text)

    def test_corrupt_manifest_and_missing_values_do_not_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / "manifest.json").write_text("not json", encoding="utf-8")
            self.assertIn("報告是空的", self.module.build_summary(directory))

            report = {"finalUrl": "https://example.test/", "categories": {}, "audits": {}}
            self._write_reports(directory, [report])
            text = self.module.build_summary(directory, base_url="https://example.test")
        # 缺少資料時顯示破折號，而不是出錯。
        self.assertIn("| `/` | — | — | — | — — | — — | — — |", text)
        self.assertNotIn("Traceback", text)


if __name__ == "__main__":
    unittest.main()
