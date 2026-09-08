# Commands

run_demo.py reproduces one or all synthetic pipelines. check_repository.py checks local notebook and documentation contracts. prepare_hf.py packages an explicit synthetic allowlist for later inspection. No script publishes empirical data or calls a live collection service.

For local notebook execution use `python3 scripts/check_notebooks.py`. Add `--public-clone` to execute each notebook against its pinned public code checkout. No hosted Colab session is implied by this check.
