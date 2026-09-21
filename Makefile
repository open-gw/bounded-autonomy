# bounded-autonomy Makefile
# Every target listed in `make help` is the public interface.
# Versions: rig/versions.yaml

SHELL := /bin/bash
.DEFAULT_GOAL := help
.PHONY: help tools test validate up down run analyse stores-smoke clean \
	notebook fixtures

ROOT    := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
PYTHON  ?= $(firstword $(wildcard $(ROOT)/.venv/bin/python) python3)
PIP     ?= $(PYTHON) -m pip
PROFILE ?= long-multistep
MODE    ?= full
SEED    ?= 1
MANIFEST ?=

export PYTHONPATH := $(ROOT):$(ROOT)/analysis:$(ROOT)/rig:$(PYTHONPATH)

help: ## List targets
	@awk 'BEGIN {FS = ":.*##"; printf "bounded-autonomy  Paper 1 rig\n\n"} \
	     /^[a-zA-Z0-9_.-]+:.*##/ { printf "  %-16s %s\n", $$1, $$2 }' $(MAKEFILE_LIST)
	@printf "\n  PROFILE=$(PROFILE)  MODE=$(MODE)  SEED=$(SEED)\n"

tools: ## Install pinned k3d/kubectl/helm/cilium/hubble CLIs into .tools/
	$(PYTHON) $(ROOT)/scripts/install_tools.py

test: ## Schema + metric unit tests (no cluster)
	$(PYTHON) -m pytest -q $(ROOT)/tests

validate: ## Validate a run manifest (MANIFEST=runs/manifests/x.yaml)
	@if [ -z "$(MANIFEST)" ]; then echo "MANIFEST= is required" >&2; exit 2; fi
	$(PYTHON) $(ROOT)/scripts/validate_manifest.py $(MANIFEST)

fixtures: ## Write synthetic result.json + parquet fixtures used by the notebook
	$(PYTHON) $(ROOT)/scripts/build_fixtures.py

notebook: fixtures ## Run the pre-registered notebook on synthetic fixtures
	$(PYTHON) $(ROOT)/scripts/run_notebook.py

analyse: ## Emit the three manuscript tables from runs/results/**/result.json
	$(PYTHON) $(ROOT)/analysis/tables.py --results $(ROOT)/runs/results --out $(ROOT)/analysis/output

up: ## Bring up k3d + Cilium + SPIRE + stores + observers
	$(ROOT)/scripts/cluster_up.sh

down: ## Tear down the k3d cluster and local mounts
	$(ROOT)/scripts/cluster_down.sh

run: ## Execute one profile (PROFILE MODE SEED)
	$(PYTHON) -m harness.driver --profile $(PROFILE) --mode $(MODE) --seed $(SEED)

stores-smoke: ## Write and read one object per store; confirm history/versioning
	$(PYTHON) $(ROOT)/scripts/stores_smoke.py

clean: ## Remove local analysis output and .tools (not the cluster)
	rm -rf $(ROOT)/analysis/output $(ROOT)/.tools $(ROOT)/.pytest_cache
