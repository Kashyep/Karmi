PYTHON ?= python

.PHONY: doctor dev worker lint typecheck test-unit test-integration test-e2e test-smoke benchmark-demo test-release parakh-contract

doctor dev worker lint typecheck test-unit test-integration test-e2e test-smoke benchmark-demo test-release parakh-contract:
	$(PYTHON) scripts/tasks.py $@

