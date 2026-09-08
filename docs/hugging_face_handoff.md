# Later Hugging Face handoff

The GitHub template includes an offline packaging script and a dataset-card worksheet; it does not upload to Hugging Face. The real data host, account and release have not been selected here.

Run `python3 scripts/prepare_hf.py --demo` to produce `dist/hugging_face_demo/`. It verifies archived data against frozen references before copying an explicit allowlist of synthetic component files, linkage and unmatched tables, dictionary, provenance and a card with three configurations: `on_chain`, `off_chain`, `integration`. Inspect the package and checksums before any intentional upload. Existing destination contents cause a stop, preventing stale files from being silently included.

For research data, implement a separate reviewed allowlist based on source rights and privacy decisions. Replace the card text, choose component licenses and access, include an inspection sample for large data, and record an immutable hosting revision. Test that each configuration loads independently and that integration can acquire both exact component releases.

Generate and validate Croissant for actual hosted files; include responsible-AI metadata from `templates/RAI_WORKSHEET.md`. Keep a dated validator receipt and test downloads without author credentials under the intended access policy. The worksheet is not a validated Croissant file. A host's generated metadata may need additional responsible-AI fields. Follow [official NeurIPS hosting instructions](https://neurips.cc/Conferences/2026/EvaluationsDatasetsHosting) and [official Hugging Face dataset-card documentation](https://huggingface.co/docs/hub/datasets-cards).
