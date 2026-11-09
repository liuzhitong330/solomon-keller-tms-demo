"""Offline response-report serialization against pinned NaviNIBS source.

This is a bounded metadata adapter, not a NaviNIBS session or device controller.
It executes the original library's NumPy serializers without opening its GUI.

Reproduce with Python 3.12:
    python -m venv .venv
    .venv/bin/pip install attrs==26.1.0 numpy==2.3.5 pandas==2.2.3
    git clone https://github.com/PrecisionNeuroLab/NaviNIBS ../NaviNIBS
    git -C ../NaviNIBS checkout 094f86d9204204f4a5ec125d4ab3fa995047845e
    .venv/bin/python navinibs_adapter.py --navinibs-source ../NaviNIBS \
        --input adapter_fixture.json --output adapter_audit.json
    .venv/bin/python test_navinibs_adapter.py --navinibs-source ../NaviNIBS

Optional: recreate the fixture from the original public S01 file:
    .venv/bin/pip install mne==1.8.0 scipy==1.15.3
    .venv/bin/python navinibs_adapter.py --prepare-from-fif Dataset_Aalborg/S01_epo.fif \
        --output adapter_fixture.json

See THIRD_PARTY_NOTICES.md for source, license, transformation, and scope.
No acquisition timestamps or coil coordinates are generated.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

import attrs
import numpy as np
import pandas as pd


PINNED_COMMIT = "094f86d9204204f4a5ec125d4ab3fa995047845e"
REPOSITORY = "https://github.com/PrecisionNeuroLab/NaviNIBS"
S01_SHA256 = "14b138f75749b6b1fcb5c4250b8ea0fd480b2ed78e365fe41fda5c6687c19a85"
TIME_TOLERANCE_MS = 1e-8


@attrs.define
class ResponseReport:
    """Numpy-backed QC report; not a NaviNIBS Sample or session object."""

    key: str
    time_ms: np.ndarray
    evoked_uv: np.ndarray
    trial_rms_uv: np.ndarray
    metadata: dict


ARRAY_FIELDS = ("time_ms", "evoked_uv", "trial_rms_uv")


def load_upstream(source: Path):
    source = source.resolve()
    commit = subprocess.check_output(
        ["git", "-C", str(source), "rev-parse", "HEAD"], text=True
    ).strip()
    if commit != PINNED_COMMIT:
        raise ValueError(f"Expected NaviNIBS {PINNED_COMMIT}, got {commit}")
    changes = subprocess.check_output(
        ["git", "-C", str(source), "status", "--porcelain", "--", "NaviNIBS"], text=True
    ).strip()
    if changes:
        raise ValueError("NaviNIBS source has uncommitted changes; use an unmodified pinned checkout")
    sys.path.insert(0, str(source))
    from NaviNIBS.util.numpy import attrsWithNumpyAsDict, attrsWithNumpyFromDict
    from NaviNIBS.Navigator.Model.Samples import Sample

    return attrsWithNumpyAsDict, attrsWithNumpyFromDict, Sample


def validate_report(payload: dict) -> None:
    if set(payload) != {"key", *ARRAY_FIELDS, "metadata"}:
        raise ValueError("Expected key, time_ms, evoked_uv, trial_rms_uv, metadata")
    if not isinstance(payload["key"], str) or not payload["key"]:
        raise ValueError("Report key must be a nonempty string")
    if not isinstance(payload["metadata"], dict):
        raise ValueError("metadata must be a JSON object")
    for name in ARRAY_FIELDS:
        values = np.asarray(payload[name], dtype=float)
        if values.ndim != 1 or values.size == 0 or not np.all(np.isfinite(values)):
            raise ValueError(f"{name} must be a nonempty finite 1D numeric array")
    if len(payload["time_ms"]) != len(payload["evoked_uv"]):
        raise ValueError("time_ms and evoked_uv lengths must match")
    if not np.all(np.diff(payload["time_ms"]) > 0):
        raise ValueError("time_ms must be strictly increasing")
    if np.any(np.asarray(payload["trial_rms_uv"]) < 0):
        raise ValueError("Trial RMS cannot be negative")
    json.dumps(payload["metadata"], allow_nan=False)


def roundtrip_report(payload: dict, upstream) -> dict:
    """Execute the unmodified upstream Numpy serialization functions."""
    validate_report(payload)
    to_dict, from_dict, _ = upstream
    original = from_dict(ResponseReport, copy.deepcopy(payload), npFields=ARRAY_FIELDS)
    encoded = to_dict(original, npFields=ARRAY_FIELDS)
    encoded_json = json.dumps(encoded, allow_nan=False, sort_keys=True, separators=(",", ":"))
    decoded = from_dict(ResponseReport, json.loads(encoded_json), npFields=ARRAY_FIELDS)
    arrays_equal = {
        name: bool(np.array_equal(getattr(original, name), getattr(decoded, name)))
        for name in ARRAY_FIELDS
    }
    if not all(arrays_equal.values()) or original.metadata != decoded.metadata:
        raise AssertionError("NaviNIBS serialization roundtrip changed report content")
    return {
        "key": original.key,
        "upstream_repository": REPOSITORY,
        "upstream_commit": PINNED_COMMIT,
        "upstream_license": "LGPL-3.0-only",
        "functions_executed": [
            "NaviNIBS.util.numpy.attrsWithNumpyFromDict",
            "NaviNIBS.util.numpy.attrsWithNumpyAsDict",
        ],
        "time_points": len(original.time_ms),
        "trials": len(original.trial_rms_uv),
        "array_roundtrip_equal": arrays_equal,
        "metadata_roundtrip_equal": original.metadata == decoded.metadata,
        "serialized_sha256": hashlib.sha256(encoded_json.encode()).hexdigest(),
        "scope": "Numpy-backed response report serialization only; not a NaviNIBS session or clinical validation.",
    }


def sample_preflight(event: dict) -> dict:
    """Fail closed rather than turn relative epoch time into a calendar date."""
    issues = []
    if not event.get("key"):
        issues.append("MISSING_EVENT_KEY")
    stamp = event.get("timestamp")
    if stamp is None:
        issues.append("MISSING_ACQUISITION_TIMESTAMP")
    elif not isinstance(stamp, str):
        issues.append("ACQUISITION_TIMESTAMP_MUST_BE_ISO_STRING")
    elif event.get("timestamp_basis") != "recorded_acquisition_calendar_time":
        issues.append("TIMESTAMP_NOT_DOCUMENTED_AS_ACQUISITION_TIME")
    else:
        try:
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?", stamp):
                raise ValueError("Expected complete ISO calendar datetime")
            parsed = pd.Timestamp(stamp)
            if pd.isna(parsed):
                raise ValueError("Missing timestamp")
        except (ValueError, TypeError):
            issues.append("INVALID_ACQUISITION_TIMESTAMP")
    if event.get("coilToMRITransf") is not None:
        try:
            matrix = np.asarray(event["coilToMRITransf"], dtype=float)
            if matrix.shape != (4, 4) or not np.all(np.isfinite(matrix)):
                issues.append("INVALID_COIL_TRANSFORM")
            elif not np.allclose(matrix[3], [0, 0, 0, 1]):
                issues.append("INVALID_COIL_TRANSFORM_BOTTOM_ROW")
        except (ValueError, TypeError):
            issues.append("INVALID_COIL_TRANSFORM")
    return {
        "key": event.get("key"),
        "status": "BLOCKED" if issues else "REQUIRED_FIELDS_PRESENT",
        "issues": issues,
        "recorded_coil_transform_available": event.get("coilToMRITransf") is not None,
        "note": "No timestamp or coil geometry is generated. Passing this check is not validation for live hardware or a full neuronavigation session.",
    }


def prepare_fixture(fif_path: Path) -> dict:
    """Prepare a real external-data fixture, not the main scientific analysis."""
    source_sha256 = hashlib.sha256(fif_path.read_bytes()).hexdigest()
    if source_sha256 != S01_SHA256:
        raise ValueError(f"Source checksum mismatch: expected S01 {S01_SHA256}, got {source_sha256}")
    import mne
    epochs = mne.read_epochs(fif_path, preload=True, verbose="ERROR")
    if epochs.info["meas_date"] is not None:
        raise ValueError("Expected anonymized data without calendar acquisition time; inspect changed input")
    if len(epochs) != 169 or epochs.info["sfreq"] != 400:
        raise ValueError("Expected the pinned S01 benchmark: 169 epochs at 400 Hz")
    signal_uv = epochs.get_data(picks=["C3"])[:, 0, :] * 1e6
    times_ms = epochs.times * 1000
    window = (times_ms >= 20 - TIME_TOLERANCE_MS) & (times_ms <= 60 + TIME_TOLERANCE_MS)
    return {
        "report": {
            "key": "Aalborg-S01-C3-all-preprocessed-epochs",
            "time_ms": times_ms.tolist(),
            "evoked_uv": signal_uv.mean(axis=0).tolist(),
            "trial_rms_uv": np.sqrt((signal_uv[:, window] ** 2).mean(axis=1)).tolist(),
            "metadata": {
                "dataset_url": "https://zenodo.org/records/15814468",
                "dataset_doi": "10.5281/zenodo.15814468",
                "dataset_license": "CC-BY-4.0",
                "source_file": "Dataset_Aalborg/S01_epo.fif",
                "source_sha256": source_sha256,
                "source_owner": "Couto et al., external Aalborg benchmark; not Solomon/Keller recordings",
                "preprocessed": True,
                "channel": "C3",
                "sampling_rate_hz": float(epochs.info["sfreq"]),
                "input_signal_unit": "V",
                "export_signal_unit": "microvolt",
                "epoch_count": len(epochs),
                "rms_window_ms": [20, 60],
                "rms_formula": "sqrt(mean(x_uv ** 2)) over 20 <= relative_time_ms <= 60",
                "window_boundary_tolerance_ms": TIME_TOLERANCE_MS,
                "epoch_times_are_relative_to_pulse": True,
                "acquisition_clock_available": False,
                "coil_geometry_available": False,
                "condition_labels_available": False,
                "scope": "All preprocessed epochs retained for serialization only. No additional rejection, centering, or physiological interpretation; not the main stability analysis.",
            },
        },
        "events": [
            {"key": f"S01-epoch-{index + 1:03d}", "source_epoch_index": index, "timestamp": None}
            for index in range(len(epochs))
        ],
    }


def audit_payload(source: dict, upstream) -> dict:
    """Round-trip a real report and report why a full Sample export is blocked."""
    events = source.get("events")
    if not isinstance(events, list):
        raise ValueError("events must be a list")
    if len(events) != len(source["report"]["trial_rms_uv"]):
        raise ValueError("One event record is required for each trial metric")
    preflight = [sample_preflight(event) for event in events]
    blocked = sum(event["status"] == "BLOCKED" for event in preflight)
    return {
        "report_audit": roundtrip_report(source["report"], upstream),
        "sample_summary": {
            "total": len(events),
            "blocked": blocked,
            "required_fields_present": len(events) - blocked,
            "full_samples_created": 0,
            "session_created": False,
            "meaning": "Serialization interoperability only; missing acquisition clocks prevent a truthful full Sample export.",
        },
        "sample_preflight": preflight,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--navinibs-source", type=Path)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--prepare-from-fif", type=Path)
    args = parser.parse_args()
    if args.prepare_from_fif:
        result = prepare_fixture(args.prepare_from_fif)
    else:
        if args.navinibs_source is None or args.input is None:
            parser.error("--navinibs-source and --input are required for a serialization audit")
        upstream = load_upstream(args.navinibs_source)
        source = json.loads(args.input.read_text())
        result = audit_payload(source, upstream)
    text = json.dumps(result, indent=2, allow_nan=False) + "\n"
    if args.output is not None:
        args.output.write_text(text)
    else:
        print(text, end="")


if __name__ == "__main__":
    main()

