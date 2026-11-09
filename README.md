# How stable is a TMS-evoked EEG response?

A small, offline research-software demo prepared by Cathy Liu for the Solomon / Keller laboratories. It asks whether two **disjoint, equally sized sets of stimulation trials** give similar EEG waveforms for the same person. The purpose is to make unstable estimates easy to inspect, not to choose a clinical stimulation dose.

[Interactive demo](https://liuzhitong330.github.io/solomon-keller-tms-demo/)

## What is original here?

This is a focused reanalysis of an existing, preprocessed public dataset, **not independent validation, new data collection, or reproduction of the paper's gTRCA algorithm**. The contribution is a deterministic, participant-level comparison of disjoint trial groups, an editable descriptive review rule, and a portable, tested analysis output. Non-overlap does not establish statistical independence or remove possible within-record dependencies. It demonstrates a workflow that could be adapted to another authorized dataset.

The dataset is external to the Solomon / Keller labs. Their research motivates the question; their public **NaviNIBS** code is actually used for a separate, bounded data-serialization roundtrip. Nothing here connects to a stimulator, neuronavigation system, or Stanford storage.

## Inputs, in plain language

- **Aalborg data:** 22 participants from Couto et al., *Extracting Reproducible Components from Electroencephalographic Responses to Transcranial Magnetic Stimulation with Group Task-Related Component Analysis*, *Imaging Neuroscience* (2026), [doi:10.1162/IMAG.a.1085](https://doi.org/10.1162/IMAG.a.1085). The [pinned Zenodo version](https://zenodo.org/records/15814468) is CC-BY-4.0. Each FIF contains retained trials × scalp electrodes × time samples, in volts. Analysis converts volts to microvolts.
- **These are processed epochs, not raw acquisition files.** The paper describes artifact rejection, pulse-interval repair, filtering, ICA, baseline correction and interpolation before deposit. We do not repeat that cleaning. FIF default filter/baseline fields do not reconstruct the actual processing history.
- **Missing metadata matter:** no acquisition date, real pulse timestamps, coil geometry, sham condition or behavioral-state labels are provided in these files. Sequential event integers are indices, not real clock times.
- **NaviNIBS dependency:** [PrecisionNeuroLab/NaviNIBS](https://github.com/PrecisionNeuroLab/NaviNIBS), commit `094f86d9204204f4a5ec125d4ab3fa995047845e`. Unchanged NumPy serialization helpers are loaded from a separate checkout. Its LGPL license is preserved; source code is not copied into this project.

## Analysis decisions

1. Include every Aalborg participant, without choosing recordings based on their results.
2. Fix three channels (C3, Cz, Pz), two inclusive windows (20–60 ms and 80–180 ms), and five budgets (10, 20, 30, 40, 50 trials **per group**) before inspecting outcomes. These are exploratory readouts, not isolated physiological components. The early window contains only 17 samples; the later window contains 41.
3. For each participant and budget, draw 100 deterministic pairs of equal-sized groups. The groups share **no trials within a split**. Different splits reuse the same finite trials and are not independent experiments. The same assignments are used across channels and windows.
4. Average each group. Compare **shape** using Pearson correlation and **amplitude** using `200 × |RMS(A) − RMS(B)| / (RMS(A) + RMS(B))`. Zero/undefined denominators are missing, not perfect agreement. Correlation alone can hide amplitude differences; amplitude agreement alone can hide different shapes.
5. Report median and 10th–90th percentiles across the resampling draws. These are **resampling spread, not confidence intervals**. No p-values or sample-size claims are based on the time samples or resampling draws.
6. The example waveform always uses the first seeded split, never the most flattering one. A full-data mean is context only; it is not the agreement reference because it contains both groups.
7. The adjustable default rule requires lower-decile correlation ≥ 0.8 and median amplitude discrepancy ≤ 20%. It is an illustrative review rule, **not a validated QC threshold, exclusion rule, diagnostic criterion, or stimulation recommendation**. Changing it shows how much the review queue depends on the analyst's choice.

## How to interpret the page

### Results at the fixed C3 / 20–60 ms readout

All 22 participants and 3,487 retained trials were included (110–181 trials per participant). Moving from 10 to 50 trials per disjoint group, the median participant's lower-decile shape correlation rose from **0.727 to 0.940**, and the median of participants' median RMS discrepancies fell from **20.6% to 10.3%**. These are descriptive results for this readout, not population estimates or a recommended pulse count.

Under the illustrative two-metric rule, the number meeting the rule was **9, 13, 15, 14, 16 of 22** at budgets 10, 20, 30, 40, 50. More trials did not produce a strictly monotonic classification sequence. At 50, S05, S10, S15, S18, S20 and S21 remained outside the rule; some had high shape agreement but variable amplitude. Changing channels, windows or thresholds changes the result.

Three useful views, regenerated by the analysis:

- [Trial-budget sensitivity](figures/trial-budget.svg): participant-level shape and amplitude summaries.
- [Two-dimensional participant review](figures/participant-review.svg): shape and amplitude side by side, at the fixed largest budget.
- [Prespecified S01 example](figures/disjoint-example.svg): the first seeded split, not a selected success.

Start with the default S01 / C3 / 20–60 ms readout. Change the trial budget and inspect the waveform, correlation and amplitude disagreement together. Then compare the cohort under exactly the same channel/window/settings. A record outside the rule needs investigation, not automatic removal. A record inside the rule is repeatable under these within-record resamples, not necessarily biologically specific or stable across another day.

The useful next question is: **does within-record agreement predict repeatability in a separately acquired session, when pulse timing, coil position and sensory controls are available?** That requires new data; this demo cannot answer it.

## Reproduce

The primary analysis was run with Python 3.9.6 and the versions in `requirements.txt`. The first run downloads approximately 391 MB from the open, versioned archive, checks its published MD5, validates archive members and the extracted inputs, and requires all 22 participants.

```sh
python3.9 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m unittest -v test_analysis
.venv/bin/python -m analysis.run --download --output .
.venv/bin/python -m http.server 8000 --bind 127.0.0.1
```

Open `http://127.0.0.1:8000`. Checked-in outputs let the interactive page run without Python or downloading EEG. To rerun from already downloaded files, replace `--download` with `--archive data/raw/Dataset_Aalborg.zip --data-dir data/raw/Dataset_Aalborg`.

`analysis.json` contains participant-level metrics and explicitly indexed example splits; `results.csv` contains all participant/channel/window/budget summaries; `source_manifest.json` records input hashes, schema checks and analysis settings. The figures are regenerable by the same command. Different library versions may change final floating-point digits; use pinned versions for exact comparisons.

The **optional NaviNIBS adapter** requires its own Python 3.12 environment because that upstream project cannot run in the original analysis's Python 3.9 environment. Follow [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for its separate pinned commands. It reads the real S01-derived `adapter_fixture.json`; the output `adapter_audit.json` verifies numerical roundtrip and blocks full Sample export when acquisition timestamps are absent. Its synthetic unit tests are software fixtures only, never scientific observations.

## Limitations and accurate claims

There is no sham or sensory-control comparison here: muscle, auditory or somatosensory contamination can also repeat reliably. Small windows, filtering, finite-trial reuse and channel choice affect these metrics. The five budgets stop at 50 trials per group; this is not a recommendation that 100 total pulses are enough. The cohort is not a clinical outcome or seizure-state prediction dataset. Within-record resampling is not a test–retest experiment.

An accurate outreach description is: “I built an offline tool that uses a public TMS-EEG dataset to inspect how waveform and amplitude agreement vary across disjoint trial groups, with reproducible code and explicit metadata checks.” Do not call it a closed-loop system, an independently validated biomarker, a hardware integration, or evidence of hands-on TMS experience.

Implementation and documentation are AI-assisted. The artifact is transparent evidence of a proposed analytical workflow, not proof of unaided software authorship or experimental competence. Cathy's contact details are included with her authorization; no application documents, referee details or credentials are published.

## Attribution

Please cite the original dataset/paper and retain CC-BY-4.0 attribution for the derived outputs. Original project code is MIT; separately obtained NaviNIBS remains LGPL-3.0-only. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and [source_manifest.json](source_manifest.json).
