.PHONY: test lint release-smoke release-contract reproduce-release
test:
	python3 -m unittest discover -s tests -v
lint:
	python3 scripts/check_repository.py
release-smoke:
	python3 scripts/run_demo.py --track all
release-contract: test lint
reproduce-release: release-smoke
