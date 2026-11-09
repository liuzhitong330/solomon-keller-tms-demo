"""Deterministic disjoint-replicate sensitivity analysis, not gTRCA reproduction.

Run from repository root:
    python -m analysis.run --download --output .
or provide the verified local archive and its extracted dataset directory.
"""
from pathlib import Path
import argparse
import csv
import hashlib
import json
import platform
import zipfile
import zlib
import numpy as np
import mne
from .download import URL, SIZE, MD5, fetch, file_hash, verify_archive

CHANNELS = ("C3", "Cz", "Pz")
WINDOWS = {
    "early": {"label": "Early response", "start_ms": 20, "end_ms": 60},
    "late": {"label": "Later response", "start_ms": 80, "end_ms": 180},
}
BUDGETS = (10, 20, 30, 40, 50)
ITERATIONS = 100
SEED = 20261109


def stable_seed(subject, seed=SEED):
    # Stable across Python processes and platforms (unlike Python's hash()).
    return int.from_bytes(hashlib.sha256(f"{seed}:{subject}".encode()).digest()[:8], "big")


def split_indices(n_epochs, n, subject, iterations=ITERATIONS, seed=SEED):
    if n <= 0 or iterations <= 0 or 2 * n > n_epochs:
        raise ValueError("Need positive budgets and at least 2n distinct retained epochs")
    rng = np.random.default_rng(stable_seed(subject, seed))
    permutations = np.stack([rng.permutation(n_epochs) for _ in range(iterations)])
    # Same participant permutations reused across budgets; splits are not independent subjects.
    return permutations[:, :n], permutations[:, n:2 * n]


def window_mask(time_ms, start_ms, end_ms):
    t = np.asarray(time_ms, dtype=float)
    mask = (t >= start_ms - 1e-8) & (t <= end_ms + 1e-8)
    if mask.sum() < 3:
        raise ValueError("A response window must contain at least three samples")
    return mask


def waveform_metrics(a, b):
    """Rows are paired mean waveforms, columns are time points; null on degeneracy.

    r compares demeaned shape. RMS uses the un-demeaned response within the
    window; no new baseline correction is applied to author-processed epochs.
    """
    a, b = np.asarray(a, float), np.asarray(b, float)
    if a.shape != b.shape or a.ndim != 2 or a.shape[1] < 3:
        raise ValueError("Expected matching two-dimensional waveform arrays")
    finite = np.isfinite(a).all(axis=1) & np.isfinite(b).all(axis=1)
    ac, bc = a - a.mean(axis=1, keepdims=True), b - b.mean(axis=1, keepdims=True)
    den = np.sqrt(np.sum(ac * ac, axis=1) * np.sum(bc * bc, axis=1))
    r = np.full(a.shape[0], np.nan)
    valid_r = finite & (den > 0)
    r[valid_r] = np.clip(np.sum(ac[valid_r] * bc[valid_r], axis=1) / den[valid_r], -1, 1)
    rms_a, rms_b = np.sqrt(np.mean(a * a, axis=1)), np.sqrt(np.mean(b * b, axis=1))
    rms_pct = np.full(a.shape[0], np.nan)
    valid_rms = finite & ((rms_a + rms_b) > 0)
    rms_pct[valid_rms] = 200 * np.abs(rms_a[valid_rms] - rms_b[valid_rms]) / (rms_a[valid_rms] + rms_b[valid_rms])
    return r, rms_pct, rms_a, rms_b


def summary(values):
    values = np.asarray(values, float)
    good = values[np.isfinite(values)]
    if not len(good):
        return {"median": None, "p10": None, "p90": None, "n_valid": 0}
    p10, median, p90 = np.quantile(good, [0.1, 0.5, 0.9], method="linear")
    return {"median": float(median), "p10": float(p10), "p90": float(p90), "n_valid": len(good)}


def number(x):
    return float(x) if np.isfinite(x) else None


def curve(values):
    # Microvolt precision of 1e-6 is far below any inferential precision here.
    return np.round(np.asarray(values, float), 6).tolist()


def analyze_subject(subject, epochs_uv, time_ms, channels=CHANNELS):
    epochs_uv = np.asarray(epochs_uv, float)
    if epochs_uv.ndim != 3 or epochs_uv.shape[1] != len(channels) or epochs_uv.shape[2] != len(time_ms):
        raise ValueError("Expected epochs × fixed channels × time")
    if not np.isfinite(epochs_uv).all():
        raise ValueError("Non-finite retained epochs; do not silently discard trials")
    n_epochs = len(epochs_uv)
    result = {
        "id": subject, "n_epochs": n_epochs,
        "full_mean_uv": {c: curve(epochs_uv[:, j].mean(axis=0)) for j, c in enumerate(channels)},
        "readouts": {c: {} for c in channels},
    }
    masks = {key: window_mask(time_ms, w["start_ms"], w["end_ms"]) for key, w in WINDOWS.items()}
    for channel in channels:
        for key, mask in masks.items():
            result["readouts"][channel][key] = {"time_ms": curve(np.asarray(time_ms)[mask]), "budgets": []}
    for n in BUDGETS:
        if 2 * n > n_epochs:
            for channel in channels:
                for key in WINDOWS:
                    result["readouts"][channel][key]["budgets"].append({"n": n, "available": False, "reason": "fewer_than_2n_retained_epochs"})
            continue
        ai, bi = split_indices(n_epochs, n, subject)
        amean, bmean = epochs_uv[ai].mean(axis=1), epochs_uv[bi].mean(axis=1)
        for j, channel in enumerate(channels):
            for key, mask in masks.items():
                a, b = amean[:, j, mask], bmean[:, j, mask]
                r, rms, rms_a, rms_b = waveform_metrics(a, b)
                rs, ds = summary(r), summary(rms)
                passed = bool(rs["n_valid"] == ITERATIONS and ds["n_valid"] == ITERATIONS and rs["p10"] >= 0.8 and ds["median"] <= 20)
                result["readouts"][channel][key]["budgets"].append({
                    "n": n, "available": True, "r": rs, "rms_pct": ds,
                    "default_review_pass": passed,
                    "example": {
                        "a_uv": curve(a[0]), "b_uv": curve(b[0]),
                        "r": number(r[0]), "rms_pct": number(rms[0]),
                        "a_rms_uv": number(rms_a[0]), "b_rms_uv": number(rms_b[0]),
                        "a_indices": ai[0].tolist(), "b_indices": bi[0].tolist(),
                    },
                })
    return result


def load_subject(path):
    epochs = mne.read_epochs(path, preload=False, proj=False, verbose="ERROR")
    expected_times = np.arange(-240, 240) / 400
    if len(epochs.ch_names) != 63 or epochs.info["sfreq"] != 400 or not np.allclose(epochs.times, expected_times, atol=1e-12):
        raise ValueError(f"Unexpected cohort dimensions or times in {path.name}")
    if not all(c in epochs.ch_names for c in CHANNELS):
        raise ValueError(f"Missing prespecified channel in {path.name}")
    if any(t != "eeg" for t in epochs.get_channel_types()):
        raise ValueError(f"Unexpected non-EEG channel type in {path.name}")
    if any(int(ch["unit"]) != 107 for ch in epochs.info["chs"]):
        raise ValueError(f"Expected volts, not unverified amplitude units in {path.name}")
    if epochs.info["projs"]:
        raise ValueError("Unexpected projection metadata; no implicit preprocessing is permitted")
    if epochs.info["meas_date"] is not None or epochs.metadata is not None:
        raise ValueError("Source metadata changed: review clock/conditions rather than silently reinterpret")
    if not np.array_equal(epochs.events[:, 0], np.arange(len(epochs))) or not np.all(epochs.events[:, 1] == 0) or not np.all(epochs.events[:, 2] == 1):
        raise ValueError("Event schema changed: source events are expected to be artificial epoch indices")
    if epochs.event_id != {"1": 1}:
        raise ValueError("Unexpected condition labels")
    data = epochs.get_data(picks=list(CHANNELS), copy=True) * 1e6
    record = {
        "file": path.name, "sha256": file_hash(path), "n_retained_epochs": len(epochs),
        "n_channels": len(epochs.ch_names), "n_times": len(epochs.times), "sampling_hz": 400,
        "amplitude_unit": "V (FIFF107), multiplied by 1e6 for microvolts",
        "meas_date": None, "metadata": None, "event_id": epochs.event_id,
        "event_onsets_are_artificial_ordinal_indices": True,
        "header_filter_hz": [float(epochs.info["highpass"]), float(epochs.info["lowpass"])],
        "baseline_metadata": epochs.baseline,
        "projection_count": 0,
    }
    return data, epochs.times * 1000, record


def cohort_summary(participants):
    def finite_median(values):
        values = [v for v in values if v is not None and np.isfinite(v)]
        return (float(np.median(values)) if values else None), len(values)

    out = {}
    for channel in CHANNELS:
        out[channel] = {}
        for window in WINDOWS:
            out[channel][window] = []
            for i, n in enumerate(BUDGETS):
                rows = [p["readouts"][channel][window]["budgets"][i] for p in participants]
                rows = [r for r in rows if r["available"]]
                r10, count_r10 = finite_median([r["r"]["p10"] for r in rows])
                rmed, count_rmed = finite_median([r["r"]["median"] for r in rows])
                dmed, count_dmed = finite_median([r["rms_pct"]["median"] for r in rows])
                out[channel][window].append({
                    "n": n, "n_participants": len(rows),
                    "median_participant_r_p10": r10, "n_valid_r_p10": count_r10,
                    "median_participant_r_median": rmed, "n_valid_r_median": count_rmed,
                    "median_participant_rms_pct_median": dmed, "n_valid_rms_pct_median": count_dmed,
                    "default_review_pass_count": sum(r["default_review_pass"] for r in rows),
                })
    return out


def verify_extracted_files(archive, files):
    """Prevent an unrelated/modified --data-dir being trusted by archive hash alone."""
    with zipfile.ZipFile(archive) as handle:
        for path in files:
            entry = handle.getinfo("Dataset_Aalborg/" + path.name)
            crc, length = 0, 0
            with path.open("rb") as source:
                for block in iter(lambda: source.read(1024 * 1024), b""):
                    length += len(block)
                    crc = zlib.crc32(block, crc)
            if length != entry.file_size or crc & 0xFFFFFFFF != entry.CRC:
                raise ValueError(f"Extracted file differs from verified archive: {path.name}")


def write_results_csv(path, participants):
    rows = []
    for p in participants:
        for channel in CHANNELS:
            for window in WINDOWS:
                for b in p["readouts"][channel][window]["budgets"]:
                    row = {"participant": p["id"], "retained_epochs": p["n_epochs"], "channel": channel, "window": window, "n_per_replicate": b["n"], "available": b["available"]}
                    for metric in ["r", "rms_pct"]:
                        for field in ["p10", "median", "p90", "n_valid"]:
                            row[f"{metric}_{field}"] = b.get(metric, {}).get(field)
                    row["illustrative_review_pass"] = b.get("default_review_pass")
                    rows.append(row)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--data-dir", type=Path, default=Path("data/raw/Dataset_Aalborg"))
    parser.add_argument("--archive", type=Path, default=Path("data/raw/Dataset_Aalborg.zip"))
    parser.add_argument("--output", type=Path, default=Path("."))
    args = parser.parse_args()
    if args.download:
        args.archive, args.data_dir = fetch(args.archive.parent)
    verify_archive(args.archive)
    files = sorted(args.data_dir.glob("S??_epo.fif"))
    if [p.name for p in files] != [f"S{i:02d}_epo.fif" for i in range(1, 23)]:
        raise ValueError("The complete 22-participant cohort is required; no outcome-based selection")
    verify_extracted_files(args.archive, files)
    participants, sources = [], []
    for path in files:
        data, time_ms, source = load_subject(path)
        sources.append(source)
        participants.append(analyze_subject(path.stem.split("_")[0], data, time_ms))
        print(f"Analyzed {path.name}: {len(data)} retained epochs", flush=True)
    payload = {
        "meta": {
            "schema_version": "1.0.0", "artifact_mode": "APPLICATION_DEMO",
            "channels": list(CHANNELS), "windows": WINDOWS, "budgets": list(BUDGETS),
            "iterations": ITERATIONS, "seed": SEED, "time_ms": curve(time_ms),
            "n_participants": len(participants), "total_epochs": sum(p["n_epochs"] for p in participants),
            "sampling_hz": 400, "units": "microvolts", "window_endpoints_inclusive": True,
            "data_level": "External author-preprocessed individual TMS–EEG epochs",
            "source": "https://zenodo.org/records/15814468", "source_doi": "10.5281/zenodo.15814468",
            "paper_doi": "10.1162/IMAG.a.1085", "license": "CC-BY-4.0",
            "default_review_rule": {"r_p10_min": 0.8, "rms_pct_median_max": 20, "validated": False},
            "uncertainty": "Empirical 10th–90th percentiles of 100 overlapping resampling runs, not confidence intervals. The two groups within each run are disjoint.",
            "first_example_selection": "First seeded split; not chosen for a favorable result",
            "full_mean_usage": "Context only, never a reference for the agreement metrics",
            "missing_metadata": ["acquisition timestamps", "true event sample onsets", "trial chronology", "coil tracking", "sham condition", "behavioral state"],
            "preprocessing_note": "Author-processed data; no new filtering, ICA, trial rejection, channel interpolation or baseline correction. FIF header defaults are not processing-history evidence.",
        },
        "participants": participants,
        "summary": cohort_summary(participants),
    }
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "analysis.json").write_text(json.dumps(payload, separators=(",", ":"), allow_nan=False) + "\n")
    write_results_csv(args.output / "results.csv", participants)
    manifest = {
        "dataset": {"record_url": "https://zenodo.org/records/15814468", "download_url": URL, "doi": "10.5281/zenodo.15814468", "concept_doi": "10.5281/zenodo.15814467", "archive_bytes": SIZE, "archive_md5": MD5, "archive_sha256": file_hash(args.archive), "license": "CC-BY-4.0", "ownership": "External Aalborg cohort, not Solomon/Keller-acquired data"},
        "publication": {"title": "Extracting reproducible components from electroencephalographic responses to transcranial magnetic stimulation with group task-related component analysis", "doi": "10.1162/IMAG.a.1085", "url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC12784221/", "relationship": "Public processed input reused; this analysis does not reproduce gTRCA or independently validate its published claims"},
        "analysis": {"python": platform.python_version(), "numpy": np.__version__, "mne": mne.__version__, "seed": SEED, "iterations": ITERATIONS, "channels": CHANNELS, "windows": WINDOWS, "budgets_per_disjoint_group": BUDGETS, "correlation": "Pearson correlation of two demeaned within-window mean waveforms", "amplitude": "200 * abs(RMS_A-RMS_B)/(RMS_A+RMS_B); RMS uses un-demeaned within-window response", "quantiles": "NumPy linear quantiles", "rounding": "Curves rounded to 1e-6 microvolts, metrics unrounded", "input_preprocessing": "None beyond selecting fixed channels/windows and converting V to microvolts", "biological_unit": "participant; resampled splits and channels are not independent participants"},
        "files": sources,
        "output_hashes": {"analysis.json": file_hash(args.output / "analysis.json"), "results.csv": file_hash(args.output / "results.csv")},
    }
    (args.output / "source_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    from .figures import make_figures
    make_figures(payload, args.output / "figures")
    print(json.dumps({"participants": len(participants), "total_epochs": payload["meta"]["total_epochs"], "prespecified_C3_early": payload["summary"]["C3"]["early"]}, indent=2))


if __name__ == "__main__":
    main()
