"""Run: python -m unittest -v test_analysis.py"""
from pathlib import Path
import json
import unittest
import tempfile
import zipfile
import numpy as np
from analysis.run import split_indices, waveform_metrics, window_mask, summary, analyze_subject, cohort_summary, verify_extracted_files, SEED


class NumericalTests(unittest.TestCase):
    def test_disjoint_deterministic_budget_and_range(self):
        for n in [10, 20, 30, 40, 50]:
            a, b = split_indices(110, n, "S03")
            a2, b2 = split_indices(110, n, "S03")
            np.testing.assert_array_equal(a, a2)
            np.testing.assert_array_equal(b, b2)
            self.assertEqual(a.shape, (100, n))
            for ai, bi in zip(a, b):
                self.assertEqual(len(set(ai) | set(bi)), 2 * n)
                self.assertFalse(set(ai) & set(bi))
                self.assertTrue(np.all(ai >= 0) and np.all(bi < 110))
        different, _ = split_indices(110, 10, "S03", seed=SEED + 1)
        self.assertFalse(np.array_equal(different, split_indices(110, 10, "S03")[0]))

    def test_invalid_budget(self):
        for n in [0, -1, 56]:
            with self.assertRaises(ValueError):
                split_indices(110, n, "S03")

    def test_pearson_and_symmetric_amplitude_formula(self):
        a = np.asarray([[1, 2, 3], [1, 2, 3]], float)
        b = np.asarray([[2, 4, 6], [-1, -2, -3]], float)
        r, d, ra, rb = waveform_metrics(a, b)
        np.testing.assert_allclose(r, [1, -1])
        np.testing.assert_allclose(d, [200 / 3, 0])
        np.testing.assert_allclose(ra, np.sqrt([14 / 3, 14 / 3]))
        np.testing.assert_allclose(rb, [2 * ra[0], ra[1]])
        r2, d2, _, _ = waveform_metrics(b, a)
        np.testing.assert_allclose(r, r2)
        np.testing.assert_allclose(d, d2)

    def test_zero_constant_and_nonfinite_are_not_perfect_agreement(self):
        a = np.asarray([[0, 0, 0], [1, 1, 1], [np.nan, 2, 3]], float)
        r, d, _, _ = waveform_metrics(a, a)
        self.assertTrue(np.isnan(r).all())
        self.assertTrue(np.isnan(d[0]) and np.isnan(d[2]))
        self.assertEqual(d[1], 0)
        self.assertEqual(summary(r), {"median": None, "p10": None, "p90": None, "n_valid": 0})

    def test_inclusive_endpoints_and_float_tolerance(self):
        time = np.arange(-240, 240) / 400 * 1000
        early = window_mask(time, 20, 60)
        late = window_mask(time, 80, 180)
        self.assertEqual(early.sum(), 17)
        self.assertEqual(late.sum(), 41)
        np.testing.assert_allclose(time[early][[0, -1]], [20, 60])
        self.assertEqual(window_mask(time + 1e-10, 20, 60).sum(), 17)

    def test_quantiles_exclude_missing_but_report_count(self):
        s = summary([0, 1, 2, 3, 4, np.nan])
        self.assertEqual(s["n_valid"], 5)
        np.testing.assert_allclose([s["p10"], s["median"], s["p90"]], [0.4, 2, 3.6])

    def test_insufficient_trials_and_nonfinite_fail_closed(self):
        time = np.arange(-240, 240) / 400 * 1000
        data = np.ones((19, 3, 480))
        result = analyze_subject("test", data, time)
        self.assertTrue(all(not b["available"] for b in result["readouts"]["C3"]["early"]["budgets"]))
        data[0, 0, 0] = np.nan
        with self.assertRaises(ValueError):
            analyze_subject("test", data, time)

    def test_degenerate_cohort_summary_reports_missing(self):
        time = np.arange(-240, 240) / 400 * 1000
        result = analyze_subject("zero", np.zeros((100, 3, 480)), time)
        s = cohort_summary([result])["C3"]["early"][0]
        self.assertIsNone(s["median_participant_r_p10"])
        self.assertIsNone(s["median_participant_rms_pct_median"])
        self.assertEqual(s["n_valid_r_p10"], 0)
        self.assertEqual(s["default_review_pass_count"], 0)

    def test_extracted_file_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive, source = root / "source.zip", root / "S01_epo.fif"
            with zipfile.ZipFile(archive, "w") as handle:
                handle.writestr("Dataset_Aalborg/S01_epo.fif", b"original")
            source.write_bytes(b"original")
            verify_extracted_files(archive, [source])
            source.write_bytes(b"modified")
            with self.assertRaises(ValueError):
                verify_extracted_files(archive, [source])


@unittest.skipUnless(Path("analysis.json").exists(), "Run the cohort analysis first")
class OutputContractTests(unittest.TestCase):
    def test_full_cohort_schema_no_nonstandard_numbers(self):
        payload = json.loads(Path("analysis.json").read_text(), parse_constant=lambda value: self.fail(value))
        self.assertEqual([p["id"] for p in payload["participants"]], [f"S{i:02d}" for i in range(1, 23)])
        self.assertEqual(payload["meta"]["n_participants"], 22)
        self.assertEqual(len(payload["meta"]["time_ms"]), 480)
        for p in payload["participants"]:
            for channel in ["C3", "Cz", "Pz"]:
                self.assertEqual(len(p["full_mean_uv"][channel]), 480)
                for window, points in [("early", 17), ("late", 41)]:
                    r = p["readouts"][channel][window]
                    self.assertEqual(len(r["time_ms"]), points)
                    for b in r["budgets"]:
                        self.assertTrue(b["available"])
                        self.assertEqual(b["r"]["n_valid"], 100)
                        self.assertEqual(b["rms_pct"]["n_valid"], 100)
                        self.assertFalse(set(b["example"]["a_indices"]) & set(b["example"]["b_indices"]))
                        self.assertEqual(len(b["example"]["a_uv"]), points)
                        self.assertLessEqual(b["r"]["p10"], b["r"]["median"])
                        self.assertLessEqual(b["r"]["median"], b["r"]["p90"])


if __name__ == "__main__":
    unittest.main()
