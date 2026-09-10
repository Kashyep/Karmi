PYTHON ?= python

.PHONY: doctor dev lint typecheck test-unit test-integration test-e2e test-smoke benchmark-demo test-release

doctor dev lint typecheck test-unit test-integration test-e2e test-smoke benchmark-demo test-release:
	$(PYTHON) scripts/tasks.py $@

