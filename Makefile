.PHONY: venv check test validate plan render sandbox audit audit-host

VENV ?= .venv
export PATH := $(CURDIR)/$(VENV)/bin:$(PATH)

venv:
	python3 -m venv $(VENV) && $(VENV)/bin/pip install -r requirements-dev.txt checkov pip-audit

check:
	./scripts/check-all.sh

test:
	pytest -q

validate:
	python3 -m linuxops validate spec/baseline.yaml

plan:
	python3 -m linuxops plan spec/baseline.yaml

render:
	mkdir -p build
	python3 -m linuxops render spec/baseline.yaml provision -o build/provision.sh
	python3 -m linuxops render spec/baseline.yaml teardown -o build/teardown.sh

sandbox:
	PYTHON=$(CURDIR)/$(VENV)/bin/python ./scripts/sandbox-demo.sh

audit:
	./scripts/audit.sh --find f3 || true
