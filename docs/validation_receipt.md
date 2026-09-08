# Template validation receipt

Validation date: 2026-09-08. This receipt concerns the SYNTHETIC teaching scaffold, not an empirical dataset or journal submission.

| Item | Recorded evidence |
|---|---|
| Repository | https://github.com/sunshineluyao/Web3AI4IO-SD-Template |
| Executed immutable pipeline commit | `9af469f9ede69dc6ed3daef7fbc9fc5fe3d75f1d` |
| Public data location and revision | Bundled `data/` at that commit; `synthetic-v1` |
| Release mechanism | Reviewed template branch merged through a pull request; the final main SHA is recorded by its merge commit |
| Code / fixture license | Existing MIT license; original Global Nomad Nexus notice preserved |
| Reference file | `tests/reference/outputs.json` |
| Reference SHA-256 | `260b6e409928bd2078ba98f635b67785a89653dee8a5d54bff54465ebebe99f9` |
| Pipeline runtime | Python 3.12.13, Linux CPU, standard library |
| Repository checks | 136 files; 3 notebooks; 43 code cells; Python syntax, notebook structure, local file links, result paths and SVG structure passed |
| Pipeline and negative-path tests | 21 tests passed; 0 failures; 0 skips |
| Optimized Python validation | Explicit checks remain active under `python -O`; both validation commands and a negative-path regression passed |
| Full teaching reproduction | All three tracks reproduced their governed output hashes |
| Notebook execution | 43/43 code cells executed locally, each tutorial starting from its pinned public GitHub clone; receipts parsed and ZIP files checked |
| Visual check | Editable SVG rendered and inspected; no embedded raster, script or foreignObject |
| Packaging | Synthetic Hugging Face allowlist and package hashes checked; corrupted archives and existing output destinations rejected |
| Source scan | No credential-pattern findings; source repository attribution below is intentional |
| Hosted GitHub Actions | Not executed; a manually triggered workflow is supplied with pinned action commits |
| Hosted Google Colab | Not executed in the hosted service; notebook code executed locally using the pinned public checkout |
| Scientific validation | Not established; requires actual sources, reviewed labels/links, error estimates and study-specific evidence |
| Empirical/Hugging Face/Croissant release | Not performed; dataset card and responsible-AI worksheets are author templates |
| Tag / GitHub Release | Not requested or created |

## Commands used

```bash
python3 scripts/check_repository.py
python3 -m unittest discover -s tests -v
python3 scripts/run_demo.py --track all
python3 scripts/check_notebooks.py --public-clone
```

The main empirical risks remain source completeness and permissions, measurement validity, matching error, selection among linked records, time/revision provenance and supported reuse. The template records these as author work. No model is trained and no empirical causal effect is claimed; model-training/theorem-specific checks do not apply to this teaching release.

The notebook downloads are intentionally unexecuted student copies. The public-clone execution above ran their code without modifying those distributable files. After later pipeline changes, update the immutable notebook code pin only after checking the new version. The source code at the pinned commit is sufficient to reproduce the fixtures even though notebook pins and this receipt were finalized in a subsequent documentation commit.

## Repository adaptation

Copied from the validated template at https://github.com/sunshineluyao/Web3AI4IO-SD, commit `c10ca32fefbc579e07d2db64be3c927b266922eb`. Repository URLs and notebook code pins now target this destination. Data fixtures and pipeline behavior are unchanged. All 21 tests passed after adaptation; all 43 notebook code cells executed locally using fresh public clones of the new repository at `9af469f9ede69dc6ed3daef7fbc9fc5fe3d75f1d`. The checks generated valid receipts and output archives. No hosted Colab or GitHub Actions run is claimed.
