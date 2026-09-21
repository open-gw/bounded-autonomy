# Shared helpers for cluster scripts. Versions from rig/versions.yaml via python.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TOOLS="${ROOT}/.tools"
mkdir -p "$TOOLS"
export PATH="${TOOLS}:${PATH}"

if [[ -x "${ROOT}/.venv/bin/python" ]]; then
  PYTHON="${ROOT}/.venv/bin/python"
else
  PYTHON="${PYTHON:-python3}"
fi

read_pin() {
  "$PYTHON" - "$ROOT/rig/versions.yaml" "$1" <<'PY'
import sys, yaml
doc = yaml.safe_load(open(sys.argv[1]))
path = sys.argv[2].split(".")
cur = doc
for p in path:
    cur = cur[p]
print(cur)
PY
}

CILIUM_CHART="$(read_pin cni.cilium_chart)"
K3D_VER="$(read_pin cluster.k3d)"
CILIUM_CLI="$(read_pin cluster.cilium_cli)"
HELM_VER="$(read_pin cluster.helm)"
KUBECTL_VER="$(read_pin cluster.kubectl)"
HUBBLE_VER="$(read_pin cluster.hubble_cli)"
CLUSTER_NAME="bounded-autonomy"
NODE_NAME="k3d-${CLUSTER_NAME}-server-0"

k3d_bin() { "${TOOLS}/k3d" "$@"; }
helm_bin() { "${TOOLS}/helm" "$@"; }
kubectl_bin() { "${TOOLS}/kubectl" "$@"; }
cilium_bin() { "${TOOLS}/cilium" "$@"; }
hubble_bin() { "${TOOLS}/hubble" "$@"; }

install_tools() {
  "$PYTHON" "$ROOT/scripts/install_tools.py"
}
