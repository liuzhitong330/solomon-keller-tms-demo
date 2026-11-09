# Third-party sources and bounded reuse

## External human TMS-EEG data

The quantitative EEG data are **not Solomon or Keller lab recordings**. They come from Couto et al., *Extracting Reproducible Components from Electroencephalographic Responses to Transcranial Magnetic Stimulation with Group Task-Related Component Analysis*, Imaging Neuroscience 4 (2026; published online December 22, 2025), [article DOI](https://doi.org/10.1162/IMAG.a.1085), [Zenodo dataset v1](https://doi.org/10.5281/zenodo.15814468).

Dataset creators: Bruno Andry Nascimento Couto, Matteo Fecchio, Simone Russo, Enrico De Martino, Sara Parmigiani, Simone Sarasso, Thomas Graven-Nielsen, Daniel Ciampi de Andrade, Marcello Massimini, Mario Carmine Emiliano Rosanova, and Adenauer Girardi Casali.

The Zenodo API records the data license as **Creative Commons Attribution 4.0 International**, [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). The source archive is `Dataset_Aalborg.zip`, publisher MD5 `18f16d53a10f1b89d1dbcbfc5c89bc3d`. This demo uses derived data; it does not redistribute the entire archive. The data remain subject to their original attribution license, regardless of any license applied to this project's original software.

### Adapter fixture transformations

`adapter_fixture.json` uses only `Dataset_Aalborg/S01_epo.fif`: all 169 supplied preprocessed epochs, channel C3, 480 samples at 400 Hz. The rebuild checks its SHA-256 against `14b138f75749b6b1fcb5c4250b8ea0fd480b2ed78e365fe41fda5c6687c19a85`. Volts were converted to microvolts. The fixture contains the across-epoch arithmetic mean time course and one RMS value per epoch over **20–60 ms**, inclusive with a 1e-8 ms floating-point boundary tolerance matching the main analysis. No additional rejection, baseline centering, filter, or component model was applied for this serialization fixture. Its purpose is to test data exchange, not to provide an independent physiological result or replicate the publication's gTRCA model. The main demo's stability analysis is separate.

These epochs have no recorded calendar acquisition time or coil geometry. Their integer event indices are **not acquisition timestamps**. All 169 prospective NaviNIBS Samples are therefore blocked by the adapter's timestamp preflight. No calendar time, pose, session, or live stimulation interface is fabricated. Synthetic values appear only inside explicitly labelled software unit tests and are never used as scientific data.

## Target-lab software: NaviNIBS

NaviNIBS is by Christopher C. Cline and contributors, from the Stanford Precision Neurotherapeutics Lab. See [the original repository](https://github.com/PrecisionNeuroLab/NaviNIBS), [documentation](https://precisionneurolab.github.io/navinibs-docs/), and [the official lab publication list](https://precisionneuro.stanford.edu/publications).

Pinned version: [`094f86d9204204f4a5ec125d4ab3fa995047845e`](https://github.com/PrecisionNeuroLab/NaviNIBS/tree/094f86d9204204f4a5ec125d4ab3fa995047845e), committed October 20, 2026. Its `pyproject.toml` declares **LGPL-3.0-only**; the original [COPYING.LESSER](https://github.com/PrecisionNeuroLab/NaviNIBS/blob/094f86d9204204f4a5ec125d4ab3fa995047845e/COPYING.LESSER) and [COPYING](https://github.com/PrecisionNeuroLab/NaviNIBS/blob/094f86d9204204f4a5ec125d4ab3fa995047845e/COPYING) contain its license terms.

This repository does **not vendor or modify NaviNIBS source**. The adapter imports the unmodified `NaviNIBS.util.numpy.attrsWithNumpyAsDict` and `attrsWithNumpyFromDict` functions from a separately supplied, clean, pinned checkout. It executes them on the real-data fixture and checks lossless numerical and metadata round-trip. The `Sample` class is exercised only by a labelled synthetic schema unit test. No GUI, neuronavigation service, device connection, or hardware control is started.

This limited interoperability check is not a validated NaviNIBS integration, a full session export, a timing guarantee, or a clinical safety assessment. Neither the data authors nor the software authors endorse this independent demonstration.

## Reproduce the adapter check

Use Python 3.12. The main analysis was originally checked in a Python 3.9/MNE 1.8 environment, but the pinned NaviNIBS source requires Python 3.12 or later and cannot be imported by that Python 3.9 interpreter. Use this separate adapter environment. Clone the dependency outside this repository:

```sh
python3.12 -m venv .venv
.venv/bin/pip install attrs==26.1.0 numpy==2.3.5 pandas==2.2.3
git clone https://github.com/PrecisionNeuroLab/NaviNIBS ../NaviNIBS
git -C ../NaviNIBS checkout 094f86d9204204f4a5ec125d4ab3fa995047845e
.venv/bin/python navinibs_adapter.py --navinibs-source ../NaviNIBS --input adapter_fixture.json --output adapter_audit.json
.venv/bin/python test_navinibs_adapter.py --navinibs-source ../NaviNIBS
```

To rebuild the fixture from the original downloaded FIF file, additionally install `mne==1.8.0 scipy==1.15.3` in the Python 3.12 adapter environment, then run. The SciPy pin retains `sph_harm`, which this MNE version imports:

```sh
.venv/bin/python navinibs_adapter.py --prepare-from-fif Dataset_Aalborg/S01_epo.fif --output adapter_fixture.json
```

The checked-in audit contains no local paths or personal application material. Dependencies retain their respective licenses; this project does not claim ownership of their code or the source EEG data.
