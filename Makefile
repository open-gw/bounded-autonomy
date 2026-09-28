# bounded-autonomy Makefile
# Every target listed in `make help` is the public interface.
# Versions: rig/versions.yaml

SHELL := /bin/bash
.DEFAULT_GOAL := help
.PHONY: help tools test validate up down run analyse paper-tables stores-smoke clean \
	notebook fixtures label-race

ROOT    := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
PYTHON  ?= $(firstword $(wildcard $(ROOT)/.venv/bin/python) python3)
PIP     ?= $(PYTHON) -m pip
PROFILE ?= long-multistep
MODE    ?= full
SEED    ?= 1
GRANULARITY ?= task
VARIANT ?=
TABLE   ?=
MANIFEST ?=
GATEWAY_BYPASS ?=

export PYTHONPATH := $(ROOT):$(ROOT)/analysis:$(ROOT)/rig:$(PYTHONPATH)

help: ## List targets
	@awk 'BEGIN {FS = ":.*##"; printf "bounded-autonomy  Paper 1 rig\n\n"} \
	     /^[a-zA-Z0-9_.-]+:.*##/ { printf "  %-16s %s\n", $$1, $$2 }' $(MAKEFILE_LIST)
	@printf "\n  PROFILE=$(PROFILE)  MODE=$(MODE)  SEED=$(SEED)  GRANULARITY=$(GRANULARITY)  VARIANT=$(VARIANT)  TABLE=$(TABLE)\n"

tools: ## Install pinned k3d/kubectl/helm/cilium/hubble CLIs into .tools/
	$(PYTHON) $(ROOT)/scripts/install_tools.py

test: ## Schema + metric unit tests (no cluster)
	$(PYTHON) -m pytest -q $(ROOT)/tests

validate: ## Validate a run manifest or result.json (MANIFEST=path)
	@if [ -z "$(MANIFEST)" ]; then echo "MANIFEST= is required" >&2; exit 2; fi
	$(PYTHON) $(ROOT)/scripts/validate_manifest.py $(MANIFEST)

fixtures: ## Write synthetic result.json + parquet fixtures used by the notebook
	$(PYTHON) $(ROOT)/scripts/build_fixtures.py

notebook: fixtures ## Run the pre-registered notebook on synthetic fixtures
	$(PYTHON) $(ROOT)/scripts/run_notebook.py

analyse: ## Manuscript tables; exits 1 unless every result.json has source=cluster
	$(PYTHON) $(ROOT)/analysis/tables.py --results $(ROOT)/runs/results --out $(ROOT)/analysis/output $(if $(TABLE),--table $(TABLE),)

paper-tables: ## LaTeX-ready rows; same cluster / variance / span-count gate as analyse
	$(PYTHON) $(ROOT)/analysis/tables.py --results $(ROOT)/runs/results --out $(ROOT)/analysis/output --format latex $(if $(TABLE),--table $(TABLE),)

up: ## k3d cluster delete+create, Cilium, standalone SPIRE, stores, observers
	$(ROOT)/scripts/cluster_up.sh

down: ## k3d cluster delete (nothing else)
	$(ROOT)/scripts/cluster_down.sh

run: ## Execute one profile (PROFILE MODE SEED GRANULARITY VARIANT)
	GRANULARITY=$(GRANULARITY) VARIANT=$(VARIANT) GATEWAY_BYPASS=$(GATEWAY_BYPASS) $(PYTHON) -m harness.driver --profile $(PROFILE) --mode $(MODE) --seed $(SEED) --granularity $(GRANULARITY) $(if $(VARIANT),--variant $(VARIANT),) $(if $(filter 1 true yes,$(GATEWAY_BYPASS)),--gateway-bypass,)

stores-smoke: ## Write and read one object per store; confirm history/versioning
	$(PYTHON) $(ROOT)/scripts/stores_smoke.py

label-race: ## Q3 held-open TCP across pod relabel A→B
	$(PYTHON) -m harness.label_race --out $(ROOT)/runs/results/_label-race

clean: ## Remove local analysis output and .tools (not the cluster)
	rm -rf $(ROOT)/analysis/output $(ROOT)/.tools $(ROOT)/.pytest_cache
