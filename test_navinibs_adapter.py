"""Adapter tests. Synthetic software fixtures are never mixed with EEG data.

Usage: python test_navinibs_adapter.py --navinibs-source ../NaviNIBS
"""

import argparse
import copy
import json
from pathlib import Path
import tempfile
import unittest

import pandas as pd

from navinibs_adapter import audit_payload, load_upstream, prepare_fixture, roundtrip_report, sample_preflight, validate_report


UPSTREAM = None


def synthetic_report():
    return {
        "key": "synthetic-unit-test-only",
        "time_ms": [-1.0, 0.0, 1.0],
        "evoked_uv": [0.0, 0.5, -0.25],
        "trial_rms_uv": [1.0, 2.0],
        "metadata": {"purpose": "synthetic software fixture, not measured EEG"},
    }


class AdapterTests(unittest.TestCase):
    def test_upstream_report_roundtrip(self):
        result = roundtrip_report(synthetic_report(), UPSTREAM)
        self.assertTrue(all(result["array_roundtrip_equal"].values()))
        self.assertTrue(result["metadata_roundtrip_equal"])

    def test_upstream_sample_roundtrip_synthetic_only(self):
        _, _, Sample = UPSTREAM
        sample = Sample(
            key="synthetic-software-test-only", timestamp=pd.Timestamp("2000-01-01T00:00:00"),
            metadata={"purpose": "synthetic unit test, not a measured stimulation event"},
        )
        self.assertEqual(Sample.fromDict(sample.asDict()).asDict(), sample.asDict())

    def test_input_not_mutated(self):
        payload = synthetic_report()
        original = copy.deepcopy(payload)
        roundtrip_report(payload, UPSTREAM)
        self.assertEqual(payload, original)

    def test_nan_rejected(self):
        payload = synthetic_report()
        payload["evoked_uv"][0] = float("nan")
        with self.assertRaises(ValueError):
            validate_report(payload)

    def test_mismatched_timecourse_rejected(self):
        payload = synthetic_report()
        payload["evoked_uv"] = [1.0]
        with self.assertRaises(ValueError):
            validate_report(payload)

    def test_nonmonotonic_time_rejected(self):
        payload = synthetic_report()
        payload["time_ms"] = [0.0, 1.0, 0.5]
        with self.assertRaises(ValueError):
            validate_report(payload)

    def test_negative_rms_rejected(self):
        payload = synthetic_report()
        payload["trial_rms_uv"][0] = -1.0
        with self.assertRaises(ValueError):
            validate_report(payload)

    def test_relative_time_never_becomes_calendar_time(self):
        result = sample_preflight({"key": "synthetic-test", "relative_onset_s": 0.1})
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("MISSING_ACQUISITION_TIMESTAMP", result["issues"])

    def test_unproven_calendar_time_blocked(self):
        result = sample_preflight({"key": "synthetic-test", "timestamp": "2000-01-01T00:00:00"})
        self.assertEqual(result["status"], "BLOCKED")

    def test_numeric_timestamp_blocked(self):
        result = sample_preflight({
            "key": "synthetic-test", "timestamp": 0,
            "timestamp_basis": "recorded_acquisition_calendar_time",
        })
        self.assertEqual(result["status"], "BLOCKED")

    def test_incomplete_calendar_time_blocked(self):
        result = sample_preflight({
            "key": "synthetic-test", "timestamp": "2000-01-01",
            "timestamp_basis": "recorded_acquisition_calendar_time",
        })
        self.assertEqual(result["status"], "BLOCKED")

    def test_invalid_transform_blocked(self):
        result = sample_preflight({
            "key": "synthetic-test", "timestamp": "2000-01-01T00:00:00",
            "timestamp_basis": "recorded_acquisition_calendar_time", "coilToMRITransf": "unknown",
        })
        self.assertIn("INVALID_COIL_TRANSFORM", result["issues"])

    def test_event_count_mismatch_rejected(self):
        with self.assertRaises(ValueError):
            audit_payload({"report": synthetic_report(), "events": []}, UPSTREAM)

    def test_source_checksum_mismatch_rejected_before_reading_data(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "not-real-data.fif"
            path.write_bytes(b"synthetic invalid source fixture for checksum test")
            with self.assertRaisesRegex(ValueError, "Source checksum mismatch"):
                prepare_fixture(path)

    def test_real_fixture_roundtrip_and_169_blocked_events(self):
        fixture = json.loads(Path(__file__).with_name("adapter_fixture.json").read_text())
        result = audit_payload(fixture, UPSTREAM)
        self.assertEqual(result["report_audit"]["time_points"], 480)
        self.assertEqual(result["report_audit"]["trials"], 169)
        self.assertTrue(all(result["report_audit"]["array_roundtrip_equal"].values()))
        self.assertEqual(result["sample_summary"]["blocked"], 169)
        self.assertEqual(result["sample_summary"]["full_samples_created"], 0)
        self.assertFalse(result["sample_summary"]["session_created"])

    def test_checked_in_audit_matches_current_fixture(self):
        fixture = json.loads(Path(__file__).with_name("adapter_fixture.json").read_text())
        saved = json.loads(Path(__file__).with_name("adapter_audit.json").read_text())
        self.assertEqual(audit_payload(fixture, UPSTREAM), saved)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--navinibs-source", type=Path, required=True)
    args, remaining = parser.parse_known_args()
    UPSTREAM = load_upstream(args.navinibs_source)
    unittest.main(argv=[__file__, *remaining])
