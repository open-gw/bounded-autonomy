# bounded-autonomy

Containing and Unwinding the Blast Radius of Agentic Workflows — Paper 1 artefact.

One-node k3d rig. One profile (`long-multistep`). Two modes (`flat`, `full`). Five seeds. Four metric exporters. Nothing from Paper 2 is in this repository.

Cite this repository via [`CITATION.cff`](CITATION.cff) until an arXiv DOI exists. Table/figure → command map: [`ARTIFACT.md`](ARTIFACT.md).

## What a run measures

Given a 30-step agent task that declares three of eight services:

- **Reach** — how many services the task identity can actually touch (`flat` expects 8, `full` expects 3).
- **Credentials** — SVIDs issued per task (one).
- **Rollback** — completeness against store-level ground truth, per write class.
- **Overhead** — extra time in `verify` spans relative to the same-seed `flat` baseline.

Definitions: [`docs/study-design.md`](docs/study-design.md). Architecture: [`docs/design.md`](docs/design.md).

## Prerequisites

Personal machine, personal accounts. Docker 27+ running, and the invoking user able to run `docker` without sudo. Clone this repository with git, then the Makefile installs the remaining pinned CLIs into `.tools/` on `make tools` (also invoked by `make up`).

- git
- GNU make
- Docker 27+ (`docker` on PATH, daemon up, user in the `docker` group)
- Python 3.12 (3.13 works; CI and `rig/versions.yaml` pin 3.12.8) with the stdlib `venv` module
- ~8 GiB RAM free for the single-node cluster

A clean Ubuntu 24.04 cloud image has Python 3.12 and git, but not `make` or `python3-venv`. `python3 -m venv` fails until that package is installed:

```bash
sudo apt-get update
sudo apt-get install -y git make python3 python3-venv
git clone git@github.com:open-gw/bounded-autonomy.git
cd bounded-autonomy
```

`make up` drops the host `/sys/fs/cgroup` bind on Linux cgroup v2 (bind-mounting it into a `cgroupns=private` k3d node makes kubelet fail with `cgroup.procs: no such file or directory`) and mounts bpf inside the node when the host has no bpffs.

Pinned versions: [`rig/versions.yaml`](rig/versions.yaml). Nothing floats.

## One profile, end to end

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt

make help
make test          # schema + metrics; no cluster
make tools         # pinned k3d/kubectl/helm/cilium/hubble into .tools/
make up            # k3d delete+create, Cilium, standalone SPIRE, stores
make run PROFILE=long-multistep MODE=full SEED=1
make down
```

Fifteen runs and the manuscript tables (cluster only). Task-granularity `flat` and `full` seeds 1–5, then five `full` runs at step granularity:

```bash
make tools
make up
for mode in flat full; do
  for seed in 1 2 3 4 5; do
    make run PROFILE=long-multistep MODE=$mode SEED=$seed
  done
done
for seed in 1 2 3 4 5; do
  make run PROFILE=long-multistep MODE=full SEED=$seed GRANULARITY=step
done
make analyse       # exits 1 unless every result.json has source=cluster
make paper-tables  # LaTeX rows; same provenance gate
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
CITATION.cff    Paper 1 citation
ARTIFACT.md     manuscript table/figure → command and files
```

## Licence

MIT. Decision record: [`docs/findings/00-bootstrap.md`](docs/findings/00-bootstrap.md).
