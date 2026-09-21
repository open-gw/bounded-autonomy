# bounded-autonomy

Containing and Unwinding the Blast Radius of Agentic Workflows — Paper 1 artefact.

One-node k3d rig. One profile (`long-multistep`). Two modes (`flat`, `full`). Five seeds. Four metric exporters. Nothing from Paper 2 is in this repository.

Citation will be added when the arXiv DOI exists. Until then, cite this repository.

## What a run measures

Given a 30-step agent task that declares three of eight services:

- **Reach** — how many services the task identity can actually touch (`flat` expects 8, `full` expects 3).
- **Credentials** — SVIDs issued per task (one).
- **Rollback** — completeness against store-level ground truth, per write class.
- **Overhead** — extra time in `verify` spans relative to the same-seed `flat` baseline.

Definitions: [`docs/study-design.md`](docs/study-design.md). Architecture: [`docs/design.md`](docs/design.md).

## Prerequisites

Personal machine, personal accounts. Docker running. The Makefile installs the remaining pinned CLIs into `.tools/` on first `make up`.

- Docker 27+
- Python 3.12 (3.13 works; CI and `rig/versions.yaml` pin 3.12.8)
- ~8 GiB RAM free for the single-node cluster

Pinned versions: [`rig/versions.yaml`](rig/versions.yaml). Nothing floats.

## One profile, end to end

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt

make help
make test          # schema + metrics; no cluster
make up            # k3d, Cilium, SPIRE, stores, observers
make run PROFILE=long-multistep MODE=full SEED=1
make down
```

Ten runs and the manuscript tables:

```bash
make up
for mode in flat full; do
  for seed in 1 2 3 4 5; do
    make run PROFILE=long-multistep MODE=$mode SEED=$seed
  done
done
make analyse       # prints the three tables; writes analysis/output/
make down
```

Validate a manifest without the cluster:

```bash
make validate MANIFEST=runs/manifests/long-multistep-full.yaml
```

## Layout

```
docs/           study design, architecture, findings, NEW-MATTER
rig/            cluster, controller, identity, stores, harness, …
runs/manifests  one YAML per planned run
runs/results    gitignored except result.json
analysis/       metrics.py, pre-registered notebook
```

## Licence

MIT. Decision record: [`docs/findings/00-bootstrap.md`](docs/findings/00-bootstrap.md).
